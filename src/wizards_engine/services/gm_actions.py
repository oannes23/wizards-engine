"""Service layer for GM direct actions (POST /api/v1/gm/actions).

Implements a dispatcher pattern: ``dispatch_gm_action`` routes to the
correct handler based on ``action_type``.  Each handler is a pure
function that mutates state and returns a committed Event.

Currently implemented handlers:
- ``handle_modify_character``: mutates character meters, skills, magic
  stats, and attributes; detects stress boundary and auto-generates a
  ``resolve_trauma`` proposal when stress hits the character's effective
  maximum.
- ``handle_modify_group``: sets the tier field on a Group.
- ``handle_modify_location``: re-parents a Location (changes parent_id)
  with circular-hierarchy protection.
- ``handle_modify_clock``: advances or sets clock progress; detects
  completion and auto-generates a ``resolve_clock`` proposal (idempotent).

Functions are stateless — all accept a SQLAlchemy ``Session`` as their
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.event import Event
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.user import User
from wizards_engine.schemas.gm_actions import (
    AwardXpRequest,
    CreateBondRequest,
    CreateEffectRequest,
    CreateTraitRequest,
    ModifyBondRequest,
    ModifyCharacterRequest,
    ModifyClockRequest,
    ModifyEffectRequest,
    ModifyGroupRequest,
    ModifyLocationRequest,
    ModifyTraitRequest,
    RetireBondRequest,
    RetireEffectRequest,
    RetireTraitRequest,
)
from wizards_engine.services.bond import create_bond as bond_service_create
from wizards_engine.services.event import VALID_VISIBILITY_LEVELS, create_event
from wizards_engine.services.magic_effect import create_effect as effect_service_create


# ---------------------------------------------------------------------------
# Meter range constraints
# ---------------------------------------------------------------------------

_METER_RANGES: dict[str, tuple[int, int]] = {
    "stress": (0, 9),
    "free_time": (0, 20),
    "plot": (0, 10_000),  # spec says >=0; use a large upper bound
    "gnosis": (0, 23),
}

_SKILL_RANGE: tuple[int, int] = (0, 3)
_MAGIC_STAT_LEVEL_RANGE: tuple[int, int] = (0, 5)
_MAGIC_STAT_XP_RANGE: tuple[int, int] = (0, 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: int, lo: int, hi: int) -> tuple[int, bool]:
    """Return ``(clamped_value, was_clamped)``.

    Args:
        value: The candidate value.
        lo: Lower bound (inclusive).
        hi: Upper bound (inclusive).

    Returns:
        A 2-tuple: the value after clamping, and ``True`` if clamping
        occurred.
    """
    if value < lo:
        return lo, True
    if value > hi:
        return hi, True
    return value, False


def _count_trauma_bonds(db: Session, character_id: str) -> int:
    """Return the count of active trauma bonds for a character.

    A trauma bond is a ``pc_bond`` slot owned by the character where
    ``is_trauma = True`` and ``is_active = True``.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to inspect.

    Returns:
        Number of active trauma bonds.
    """
    rows = (
        db.execute(
            select(Slot).where(
                and_(
                    Slot.owner_type == "character",
                    Slot.owner_id == character_id,
                    Slot.slot_type == "pc_bond",
                    Slot.is_trauma.is_(True),
                    Slot.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


def _has_pending_resolve_trauma(db: Session, character_id: str) -> bool:
    """Return ``True`` if a pending ``resolve_trauma`` proposal exists.

    Used to ensure idempotency — only one pending trauma proposal per
    character at a time.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character to check.

    Returns:
        ``True`` if a pending ``resolve_trauma`` proposal exists for
        this character.
    """
    result = db.scalars(
        select(Proposal).where(
            Proposal.character_id == character_id,
            Proposal.action_type == "resolve_trauma",
            Proposal.status == "pending",
        )
    ).first()
    return result is not None


# ---------------------------------------------------------------------------
# modify_character handler
# ---------------------------------------------------------------------------


def handle_modify_character(
    db: Session,
    user: User,
    payload: ModifyCharacterRequest,
) -> Event:
    """Apply direct GM modifications to a character and record an event.

    Mutates the character in-place, builds a ``changes`` dict with
    before/after values and clamping flags, then persists an Event.

    If the new stress value hits or exceeds the character's effective stress
    maximum (9 - trauma count), a ``resolve_trauma`` proposal is
    auto-generated (idempotent — skipped if one is already pending) and a
    silent ``character.resolve_trauma_generated`` rider event is created.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyCharacterRequest`` with ``target_id``
            and ``changes``.

    Returns:
        The primary ``character.updated`` Event created for this action.

    Raises:
        ValueError: If the target character does not exist, is not a full
            character, or the requested visibility is invalid.
    """
    character: Character | None = db.get(Character, payload.target_id)
    if character is None:
        raise ValueError(f"Character '{payload.target_id}' not found.")
    if character.detail_level != "full":
        raise ValueError(
            f"Character '{payload.target_id}' is a simplified character; "
            "meters, skills, and magic stats cannot be modified via GM actions."
        )

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    changes: dict[str, Any] = {}
    ch = payload.changes

    # ------------------------------------------------------------------
    # Meter changes
    # ------------------------------------------------------------------
    for field in ("stress", "free_time", "plot", "gnosis"):
        op_obj = getattr(ch, field)
        if op_obj is None:
            continue

        before: int = getattr(character, field) or 0
        lo, hi = _meter_range_for_field(field, character, db)

        if op_obj.op == "delta":
            raw = before + op_obj.value
        else:  # "set"
            raw = op_obj.value

        after, clamped = _clamp(raw, lo, hi)
        setattr(character, field, after)

        change_op = "meter.delta" if op_obj.op == "delta" else "meter.set"
        entry: dict[str, Any] = {
            "op": change_op,
            "before": before,
            "after": after,
        }
        if clamped:
            entry["clamped"] = True
        changes[f"character.{character.id}.{field}"] = entry

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------
    if ch.skills:
        current_skills: dict[str, int] = dict(character.skills or {})
        for skill_name, level in ch.skills.items():
            before_val = current_skills.get(skill_name, 0)
            after_val, clamped = _clamp(level, *_SKILL_RANGE)
            current_skills[skill_name] = after_val
            entry = {"op": "field.set", "before": before_val, "after": after_val}
            if clamped:
                entry["clamped"] = True
            changes[f"character.{character.id}.skills.{skill_name}"] = entry
        character.skills = current_skills

    # ------------------------------------------------------------------
    # Magic stats
    # ------------------------------------------------------------------
    if ch.magic_stats:
        current_magic: dict[str, Any] = {
            k: dict(v) for k, v in (character.magic_stats or {}).items()
        }
        for stat_name, stat_change in ch.magic_stats.items():
            stat_block = dict(current_magic.get(stat_name, {"level": 0, "xp": 0}))

            if stat_change.xp is not None:
                before_xp = stat_block.get("xp", 0)
                raw_xp = before_xp + stat_change.xp
                after_xp, xp_clamped = _clamp(raw_xp, *_MAGIC_STAT_XP_RANGE)
                stat_block["xp"] = after_xp
                entry = {"op": "meter.delta", "before": before_xp, "after": after_xp}
                if xp_clamped:
                    entry["clamped"] = True
                changes[f"character.{character.id}.magic_stats.{stat_name}.xp"] = entry

            if stat_change.level is not None:
                before_level = stat_block.get("level", 0)
                after_level, level_clamped = _clamp(
                    stat_change.level, *_MAGIC_STAT_LEVEL_RANGE
                )
                stat_block["level"] = after_level
                entry = {
                    "op": "field.set",
                    "before": before_level,
                    "after": after_level,
                }
                if level_clamped:
                    entry["clamped"] = True
                changes[
                    f"character.{character.id}.magic_stats.{stat_name}.level"
                ] = entry

            current_magic[stat_name] = stat_block

        character.magic_stats = current_magic

    # ------------------------------------------------------------------
    # Attributes — merge into the JSON blob
    # ------------------------------------------------------------------
    if ch.attributes is not None:
        before_attrs = dict(character.attributes or {})
        merged = {**before_attrs, **ch.attributes}
        character.attributes = merged
        changes[f"character.{character.id}.attributes"] = {
            "op": "field.set",
            "before": before_attrs,
            "after": merged,
        }

    # ------------------------------------------------------------------
    # last_session_time_now
    # ------------------------------------------------------------------
    if ch.last_session_time_now is not None:
        before_lst = character.last_session_time_now
        character.last_session_time_now = ch.last_session_time_now
        changes[f"character.{character.id}.last_session_time_now"] = {
            "op": "field.set",
            "before": before_lst,
            "after": ch.last_session_time_now,
        }

    db.flush()

    # ------------------------------------------------------------------
    # Determine event type based on what changed
    # ------------------------------------------------------------------
    event_type = _derive_event_type(ch)

    # ------------------------------------------------------------------
    # Create the primary event
    # ------------------------------------------------------------------
    event = create_event(
        db,
        type=event_type,
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "character",
                "target_id": character.id,
                "is_primary": True,
            }
        ],
    )

    # ------------------------------------------------------------------
    # Stress boundary check — auto-generate resolve_trauma proposal
    # ------------------------------------------------------------------
    if character.stress is not None and ch.stress is not None:
        trauma_count = _count_trauma_bonds(db, character.id)
        effective_max = 9 - trauma_count
        if character.stress >= effective_max:
            if not _has_pending_resolve_trauma(db, character.id):
                proposal = Proposal(
                    character_id=character.id,
                    action_type="resolve_trauma",
                    origin="system",
                    narrative="",
                    selections={},
                    status="pending",
                )
                db.add(proposal)
                db.flush()

                create_event(
                    db,
                    type="character.resolve_trauma_generated",
                    actor_type="system",
                    actor_id=None,
                    changes={},
                    visibility="silent",
                    parent_event_id=event.id,
                    targets=[
                        {
                            "target_type": "character",
                            "target_id": character.id,
                            "is_primary": True,
                        }
                    ],
                    metadata={"proposal_id": proposal.id},
                )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# Helpers used by the handler
# ---------------------------------------------------------------------------


def _meter_range_for_field(
    field: str,
    character: Character,
    db: Session,
) -> tuple[int, int]:
    """Return the valid (lo, hi) range for a meter field.

    For ``stress`` the upper bound is the character's effective stress max
    (9 - active trauma bond count).  All other meters use the static ranges
    from :data:`_METER_RANGES`.

    Args:
        field: The meter field name.
        character: The character being modified.
        db: Active SQLAlchemy session.

    Returns:
        A ``(lo, hi)`` tuple.
    """
    if field == "stress":
        trauma_count = _count_trauma_bonds(db, character.id)
        return (0, 9 - trauma_count)
    return _METER_RANGES[field]


def _derive_event_type(ch: Any) -> str:
    """Choose an event type string based on which change categories are present.

    Uses domain-specific types when only a single category is being changed;
    falls back to ``character.updated`` for mixed or attribute-only changes.

    Args:
        ch: The ``ModifyCharacterChanges`` object from the request.

    Returns:
        A ``{domain}.{action}`` event type string.
    """
    meter_fields = {
        f
        for f in ("stress", "free_time", "plot", "gnosis")
        if getattr(ch, f) is not None
    }
    has_skills = bool(ch.skills)
    has_magic = bool(ch.magic_stats)
    has_attrs = ch.attributes is not None
    has_lst = ch.last_session_time_now is not None

    # Single-category shortcuts
    if meter_fields and not has_skills and not has_magic and not has_attrs and not has_lst:
        if meter_fields == {"stress"}:
            return "character.stress_changed"
        if meter_fields == {"gnosis"}:
            return "character.gnosis_changed"
        return "character.meter_updated"

    if has_skills and not meter_fields and not has_magic and not has_attrs and not has_lst:
        return "character.skill_changed"

    if has_magic and not meter_fields and not has_skills and not has_attrs and not has_lst:
        return "character.magic_stat_changed"

    return "character.updated"


# ---------------------------------------------------------------------------
# modify_group handler
# ---------------------------------------------------------------------------


def handle_modify_group(
    db: Session,
    user: User,
    payload: ModifyGroupRequest,
) -> Event:
    """Apply a direct GM tier change to a Group and record an event.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyGroupRequest`` with ``target_id`` and
            ``changes.tier``.

    Returns:
        The ``group.updated`` Event created for this action.

    Raises:
        ValueError: If the target Group does not exist or the requested
            visibility is invalid.
    """
    group: Group | None = db.get(Group, payload.target_id)
    if group is None:
        raise ValueError(f"Group '{payload.target_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    before_tier: int = group.tier
    group.tier = payload.changes.tier
    db.flush()

    changes: dict[str, Any] = {
        f"group.{group.id}.tier": {
            "op": "meter.set",
            "before": before_tier,
            "after": group.tier,
        }
    }

    event = create_event(
        db,
        type="group.updated",
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "group",
                "target_id": group.id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# modify_location handler
# ---------------------------------------------------------------------------


def _collect_descendant_ids(db: Session, location_id: str) -> set[str]:
    """Return the set of all descendant IDs for a location (BFS).

    Used to detect circular parent assignments.  A location cannot be
    re-parented to one of its own descendants.

    Args:
        db: Active SQLAlchemy session.
        location_id: ULID of the location whose descendants to collect.

    Returns:
        Set of location IDs that are descendants of ``location_id``
        (not including ``location_id`` itself).
    """
    visited: set[str] = set()
    queue: list[str] = [location_id]
    while queue:
        current = queue.pop()
        children = db.execute(
            select(Location.id).where(Location.parent_id == current)
        ).all()
        for (child_id,) in children:
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)
    return visited


def handle_modify_location(
    db: Session,
    user: User,
    payload: ModifyLocationRequest,
) -> Event:
    """Re-parent a Location and record an event.

    Validates that the target location exists, the new parent (if any)
    exists, and that the assignment would not create a circular hierarchy.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyLocationRequest`` with ``target_id``
            and ``changes.parent_id``.

    Returns:
        The ``location.updated`` Event created for this action.

    Raises:
        ValueError: If the target location does not exist, the new parent
            does not exist, a circular hierarchy would result, the new
            parent is the location itself, or the visibility is invalid.
    """
    location: Location | None = db.get(Location, payload.target_id)
    if location is None:
        raise ValueError(f"Location '{payload.target_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    new_parent_id: str | None = payload.changes.parent_id

    if new_parent_id is not None:
        # Ensure the new parent exists.
        new_parent: Location | None = db.get(Location, new_parent_id)
        if new_parent is None:
            raise ValueError(f"Parent location '{new_parent_id}' not found.")

        # Cannot assign a location as its own parent.
        if new_parent_id == payload.target_id:
            raise ValueError(
                f"Location '{payload.target_id}' cannot be its own parent."
            )

        # Cannot assign a descendant as parent (would create a cycle).
        descendants = _collect_descendant_ids(db, payload.target_id)
        if new_parent_id in descendants:
            raise ValueError(
                f"Cannot set '{new_parent_id}' as the parent of "
                f"'{payload.target_id}': it is a descendant (circular hierarchy)."
            )

    before_parent_id: str | None = location.parent_id
    location.parent_id = new_parent_id
    db.flush()

    changes: dict[str, Any] = {
        f"location.{location.id}.parent_id": {
            "op": "field.set",
            "before": before_parent_id,
            "after": new_parent_id,
        }
    }

    event = create_event(
        db,
        type="location.updated",
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "location",
                "target_id": location.id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# modify_clock handler
# ---------------------------------------------------------------------------


def _has_resolve_clock_proposal(db: Session, clock_id: str) -> bool:
    """Return ``True`` if a pending or approved ``resolve_clock`` proposal exists.

    Used to enforce idempotency — only one resolve_clock proposal per
    clock, ever.

    Args:
        db: Active SQLAlchemy session.
        clock_id: ULID of the clock to check.

    Returns:
        ``True`` if a pending or approved ``resolve_clock`` proposal
        exists for this clock.
    """
    result = db.scalars(
        select(Proposal).where(
            Proposal.clock_id == clock_id,
            Proposal.action_type == "resolve_clock",
            Proposal.status.in_(["pending", "approved"]),
        )
    ).first()
    return result is not None


def handle_modify_clock(
    db: Session,
    user: User,
    payload: ModifyClockRequest,
) -> Event:
    """Apply a progress change to a Clock and record an event.

    Applies the progress delta or set operation (clamped to ``>= 0``; no
    upper hard cap — the GM may advance past the segment count).  After
    applying the change, checks for clock completion and auto-generates a
    ``resolve_clock`` proposal if needed (idempotent).

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyClockRequest`` with ``target_id``,
            ``changes.progress``, and optional ``metadata``.

    Returns:
        The ``clock.advanced`` Event created for this action.

    Raises:
        ValueError: If the target Clock does not exist or the visibility
            is invalid.
    """
    clock: Clock | None = db.get(Clock, payload.target_id)
    if clock is None:
        raise ValueError(f"Clock '{payload.target_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    before_progress: int = clock.progress
    op_obj = payload.changes.progress

    if op_obj.op == "delta":
        raw = before_progress + op_obj.value
    else:  # "set"
        raw = op_obj.value

    # Clamp: floor at 0; no upper cap (soft cap per spec).
    after_progress = max(raw, 0)
    clamped = after_progress != raw

    clock.progress = after_progress
    db.flush()

    change_op = "meter.delta" if op_obj.op == "delta" else "meter.set"
    change_entry: dict[str, Any] = {
        "op": change_op,
        "before": before_progress,
        "after": after_progress,
    }
    if clamped:
        change_entry["clamped"] = True

    changes: dict[str, Any] = {f"clock.{clock.id}.progress": change_entry}

    # Build event metadata from annotation fields.
    event_metadata: dict[str, Any] | None = None
    if payload.metadata is not None:
        event_metadata = payload.metadata.model_dump(exclude_none=True)
        if not event_metadata:
            event_metadata = None

    event = create_event(
        db,
        type="clock.advanced",
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "clock",
                "target_id": clock.id,
                "is_primary": True,
            }
        ],
        metadata=event_metadata,
    )

    # ------------------------------------------------------------------
    # Clock completion check — auto-generate resolve_clock proposal
    # ------------------------------------------------------------------
    if clock.progress >= clock.segments:
        if not _has_resolve_clock_proposal(db, clock.id):
            proposal = Proposal(
                character_id=None,
                action_type="resolve_clock",
                origin="system",
                narrative=f"Clock '{clock.name}' has completed.",
                selections={},
                calculated_effect={},
                status="pending",
                clock_id=clock.id,
            )
            db.add(proposal)
            db.flush()

            create_event(
                db,
                type="clock.resolve_generated",
                actor_type="system",
                actor_id=None,
                changes={},
                visibility="silent",
                parent_event_id=event.id,
                targets=[
                    {
                        "target_type": "clock",
                        "target_id": clock.id,
                        "is_primary": True,
                    }
                ],
                metadata={"proposal_id": proposal.id},
            )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# Bond slot type sets — used to classify slots by purpose
# ---------------------------------------------------------------------------

_BOND_SLOT_TYPES: frozenset[str] = frozenset(
    {"pc_bond", "npc_bond", "group_relation", "group_holding", "location_bond"}
)

_PC_TRAIT_SLOT_TYPES: frozenset[str] = frozenset({"core_trait", "role_trait"})

_FREEFORM_TRAIT_SLOT_TYPES: frozenset[str] = frozenset({"group_trait", "feature_trait"})

_ALL_TRAIT_SLOT_TYPES: frozenset[str] = _PC_TRAIT_SLOT_TYPES | _FREEFORM_TRAIT_SLOT_TYPES

_TRAIT_SLOT_LIMITS: dict[str, int] = {
    "core_trait": 2,
    "role_trait": 3,
}

_VALID_MAGIC_STATS: frozenset[str] = frozenset(
    {"being", "wyrding", "summoning", "enchanting", "dreaming"}
)


# ---------------------------------------------------------------------------
# create_bond handler
# ---------------------------------------------------------------------------


def handle_create_bond(
    db: Session,
    user: User,
    payload: CreateBondRequest,
) -> Event:
    """Create a bond between two Game Objects and record an event.

    Delegates validation and slot creation to the bond service (slot
    limits, duplicate prevention, slot-type auto-inference, bidirectionality
    inference).

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``CreateBondRequest``.

    Returns:
        A ``bond.created`` Event.

    Raises:
        ValueError: If the source or target does not exist, a slot limit
            is reached, a duplicate bond exists, or the pairing is invalid.
    """
    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    result = bond_service_create(
        db,
        source_type=payload.owner_type,
        source_id=payload.owner_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        source_label=payload.source_label or "",
        target_label=payload.target_label or "",
        description=payload.description or "",
        bidirectional=payload.bidirectional,
    )
    bond = result.bond

    event = create_event(
        db,
        type="bond.created",
        actor_type="gm",
        actor_id=user.id,
        changes={},
        created_objects=[{"type": "slot", "id": bond.id}],
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": payload.owner_type,
                "target_id": payload.owner_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# modify_bond handler
# ---------------------------------------------------------------------------


def handle_modify_bond(
    db: Session,
    user: User,
    payload: ModifyBondRequest,
) -> Event:
    """Apply direct GM modifications to a bond slot and record an event.

    Handles label and description changes as simple field sets.  Stress
    (charge) changes follow meter semantics: delta adds to current, set
    assigns absolute.  When stress reaches the effective max for a pc_bond
    (5 - stress_degradations), the charges reset to 0 and a degradation is
    applied automatically.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyBondRequest`` with ``bond_id`` and
            ``changes``.

    Returns:
        A ``bond.stress_changed`` or ``bond.updated`` Event.

    Raises:
        ValueError: If the bond slot does not exist or visibility is invalid.
    """
    bond: Slot | None = db.get(Slot, payload.bond_id)
    if bond is None:
        raise ValueError(f"Bond '{payload.bond_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    changes: dict[str, Any] = {}
    ch = payload.changes
    has_stress_change = False

    # ------------------------------------------------------------------
    # Label / description changes (simple field sets)
    # ------------------------------------------------------------------
    for field_name in ("source_label", "target_label", "description"):
        new_val = getattr(ch, field_name)
        if new_val is not None:
            before_val = getattr(bond, field_name)
            setattr(bond, field_name, new_val)
            changes[f"slot.{bond.id}.{field_name}"] = {
                "op": "field.set",
                "before": before_val,
                "after": new_val,
            }

    # ------------------------------------------------------------------
    # stress_degradations change
    # ------------------------------------------------------------------
    if ch.stress_degradations is not None:
        op_obj = ch.stress_degradations
        before_deg = bond.stress_degradations or 0
        if op_obj.op == "delta":
            new_deg = before_deg + op_obj.value
        else:
            new_deg = op_obj.value
        new_deg = max(0, new_deg)
        bond.stress_degradations = new_deg
        changes[f"slot.{bond.id}.stress_degradations"] = {
            "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
            "before": before_deg,
            "after": new_deg,
        }

    # ------------------------------------------------------------------
    # stress (bond charge) change — with degradation cascade on pc_bonds
    # ------------------------------------------------------------------
    if ch.stress is not None:
        op_obj = ch.stress
        before_stress = bond.stress or 0
        if op_obj.op == "delta":
            raw = before_stress + op_obj.value
        else:
            raw = op_obj.value

        has_stress_change = True

        # For pc_bonds: apply charge depletion / degradation cascade.
        if bond.slot_type == "pc_bond":
            degradations = bond.stress_degradations or 0
            effective_max = 5 - degradations
            degraded = False

            if raw >= effective_max and effective_max > 0:
                # Hit the max — apply a degradation.
                degradations += 1
                bond.stress_degradations = degradations
                new_effective_max = max(0, 5 - degradations)
                new_stress = max(0, new_effective_max)
                degraded = True

                # Record the degradation in the changes dict.
                changes[f"slot.{bond.id}.stress_degradations"] = {
                    "op": "meter.delta",
                    "before": degradations - 1,
                    "after": degradations,
                    "degraded": True,
                }
            else:
                new_stress = max(0, raw)

            bond.stress = new_stress
            entry: dict[str, Any] = {
                "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
                "before": before_stress,
                "after": new_stress,
            }
            if degraded:
                entry["degraded"] = True
            changes[f"slot.{bond.id}.stress"] = entry
        else:
            # Non-pc bonds: simple set/delta, no cascade.
            new_stress = max(0, raw)
            bond.stress = new_stress
            changes[f"slot.{bond.id}.stress"] = {
                "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
                "before": before_stress,
                "after": new_stress,
            }

    db.flush()

    # Choose event type.
    if has_stress_change and len(changes) == 1:
        event_type = "bond.stress_changed"
    elif has_stress_change:
        event_type = "bond.stress_changed"
    else:
        event_type = "bond.updated"

    event = create_event(
        db,
        type=event_type,
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": bond.owner_type,
                "target_id": bond.owner_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# retire_bond handler
# ---------------------------------------------------------------------------


def handle_retire_bond(
    db: Session,
    user: User,
    payload: RetireBondRequest,
) -> Event:
    """Retire a bond slot (set is_active = false) and record an event.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``RetireBondRequest`` with ``bond_id``.

    Returns:
        A ``bond.retired`` Event.

    Raises:
        ValueError: If the bond slot does not exist or visibility is invalid.
    """
    bond: Slot | None = db.get(Slot, payload.bond_id)
    if bond is None:
        raise ValueError(f"Bond '{payload.bond_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    before_active = bond.is_active
    bond.is_active = False
    db.flush()

    event = create_event(
        db,
        type="bond.retired",
        actor_type="gm",
        actor_id=user.id,
        changes={
            f"slot.{bond.id}.is_active": {
                "op": "field.set",
                "before": before_active,
                "after": False,
            }
        },
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": bond.owner_type,
                "target_id": bond.owner_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# create_trait handler
# ---------------------------------------------------------------------------


def handle_create_trait(
    db: Session,
    user: User,
    payload: CreateTraitRequest,
) -> Event:
    """Create a trait slot and record an event.

    Supports two paths:

    - **Template-linked** (``core_trait``, ``role_trait``): looks up the
      template, enforces slot limits and duplicate-template prevention,
      creates the slot with ``charge = 5``.
    - **Freeform** (``group_trait``, ``feature_trait``): creates a slot
      with the provided name and description.  No template, no charge.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``CreateTraitRequest``.

    Returns:
        A ``trait.created`` Event.

    Raises:
        ValueError: If required fields are missing, slot limits are reached,
            or referenced objects do not exist.
    """
    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    slot_type = payload.slot_type

    if slot_type in _PC_TRAIT_SLOT_TYPES:
        # Template-linked path.
        if payload.template_id is None:
            raise ValueError(
                f"template_id is required for slot_type '{slot_type}'."
            )

        # Validate owner is a full character.
        if payload.owner_type != "character":
            raise ValueError(
                f"slot_type '{slot_type}' can only be assigned to characters, "
                f"not '{payload.owner_type}'."
            )
        character: Character | None = db.get(Character, payload.owner_id)
        if character is None or character.is_deleted:
            raise ValueError(
                f"Character '{payload.owner_id}' not found or has been deleted."
            )
        if character.detail_level != "full":
            raise ValueError(
                f"Character '{payload.owner_id}' is simplified. "
                "PC traits require a full character."
            )

        # Validate template.
        template: TraitTemplate | None = db.get(TraitTemplate, payload.template_id)
        if template is None:
            raise ValueError(f"Trait template '{payload.template_id}' not found.")
        if template.is_deleted:
            raise ValueError(
                f"Trait template '{payload.template_id}' has been deleted."
            )

        # Validate template type matches slot type.
        _REQUIRED_TEMPLATE_TYPE = {"core_trait": "core", "role_trait": "role"}
        required_type = _REQUIRED_TEMPLATE_TYPE[slot_type]
        if template.type != required_type:
            raise ValueError(
                f"Template '{payload.template_id}' has type '{template.type}', "
                f"but slot_type '{slot_type}' requires a '{required_type}' template."
            )

        # Slot limit enforcement.
        limit = _TRAIT_SLOT_LIMITS[slot_type]
        stmt = select(Slot).where(
            and_(
                Slot.owner_type == "character",
                Slot.owner_id == payload.owner_id,
                Slot.slot_type == slot_type,
                Slot.is_active.is_(True),
            )
        )
        current_count = len(db.execute(stmt).scalars().all())
        if current_count >= limit:
            raise ValueError(
                f"Character '{payload.owner_id}' already has {current_count} "
                f"active {slot_type} instances (limit: {limit})."
            )

        # Duplicate template prevention.
        dup_stmt = select(Slot).where(
            and_(
                Slot.owner_type == "character",
                Slot.owner_id == payload.owner_id,
                Slot.template_id == payload.template_id,
                Slot.is_active.is_(True),
            )
        )
        if db.execute(dup_stmt).scalars().first() is not None:
            raise ValueError(
                f"Character '{payload.owner_id}' already has an active instance "
                f"of template '{payload.template_id}'."
            )

        slot = Slot(
            slot_type=slot_type,
            owner_type="character",
            owner_id=payload.owner_id,
            template_id=payload.template_id,
            name=template.name,
            description=payload.description or template.description,
            charge=5,
            is_active=True,
        )

    elif slot_type in _FREEFORM_TRAIT_SLOT_TYPES:
        # Freeform path.
        if not payload.name:
            raise ValueError(
                f"name is required for freeform slot_type '{slot_type}'."
            )

        slot = Slot(
            slot_type=slot_type,
            owner_type=payload.owner_type,
            owner_id=payload.owner_id,
            name=payload.name,
            description=payload.description,
            is_active=True,
        )

    else:
        raise ValueError(
            f"Invalid slot_type '{slot_type}' for create_trait. "
            "Must be one of: core_trait, role_trait, group_trait, feature_trait."
        )

    db.add(slot)
    db.flush()
    db.refresh(slot)

    event = create_event(
        db,
        type="trait.created",
        actor_type="gm",
        actor_id=user.id,
        changes={},
        created_objects=[{"type": "slot", "id": slot.id}],
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": payload.owner_type,
                "target_id": payload.owner_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# modify_trait handler
# ---------------------------------------------------------------------------


def handle_modify_trait(
    db: Session,
    user: User,
    payload: ModifyTraitRequest,
) -> Event:
    """Apply direct GM modifications to a trait slot and record an event.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyTraitRequest`` with ``trait_id`` and
            ``changes``.

    Returns:
        A ``trait.recharged`` (if only charge changed) or ``trait.updated``
        Event.

    Raises:
        ValueError: If the trait slot does not exist or visibility is invalid.
    """
    slot: Slot | None = db.get(Slot, payload.trait_id)
    if slot is None:
        raise ValueError(f"Trait '{payload.trait_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    changes: dict[str, Any] = {}
    ch = payload.changes
    has_charge_change = False

    # Name change.
    if ch.name is not None:
        before_name = slot.name
        slot.name = ch.name
        changes[f"slot.{slot.id}.name"] = {
            "op": "field.set",
            "before": before_name,
            "after": ch.name,
        }

    # Description change.
    if ch.description is not None:
        before_desc = slot.description
        slot.description = ch.description
        changes[f"slot.{slot.id}.description"] = {
            "op": "field.set",
            "before": before_desc,
            "after": ch.description,
        }

    # Charge change.
    if ch.charge is not None:
        op_obj = ch.charge
        before_charge = slot.charge if slot.charge is not None else 0
        if op_obj.op == "delta":
            raw = before_charge + op_obj.value
        else:
            raw = op_obj.value
        new_charge = max(0, raw)
        slot.charge = new_charge
        changes[f"slot.{slot.id}.charge"] = {
            "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
            "before": before_charge,
            "after": new_charge,
        }
        has_charge_change = True

    db.flush()

    # Choose event type.
    if has_charge_change and len(changes) == 1:
        event_type = "trait.recharged"
    else:
        event_type = "trait.updated"

    event = create_event(
        db,
        type=event_type,
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": slot.owner_type,
                "target_id": slot.owner_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# retire_trait handler
# ---------------------------------------------------------------------------


def handle_retire_trait(
    db: Session,
    user: User,
    payload: RetireTraitRequest,
) -> Event:
    """Retire a trait slot (set is_active = false) and record an event.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``RetireTraitRequest`` with ``trait_id``.

    Returns:
        A ``trait.retired`` Event.

    Raises:
        ValueError: If the trait slot does not exist or visibility is invalid.
    """
    slot: Slot | None = db.get(Slot, payload.trait_id)
    if slot is None:
        raise ValueError(f"Trait '{payload.trait_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    before_active = slot.is_active
    slot.is_active = False
    db.flush()

    event = create_event(
        db,
        type="trait.retired",
        actor_type="gm",
        actor_id=user.id,
        changes={
            f"slot.{slot.id}.is_active": {
                "op": "field.set",
                "before": before_active,
                "after": False,
            }
        },
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": slot.owner_type,
                "target_id": slot.owner_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# create_effect handler
# ---------------------------------------------------------------------------


def handle_create_effect(
    db: Session,
    user: User,
    payload: CreateEffectRequest,
) -> Event:
    """Create a Magic Effect on a character and record an event.

    Delegates validation and creation to the magic_effect service (character
    existence and detail_level check, effect_type validation, power_level
    range check, charge field requirements, cap enforcement for
    charged/permanent effects).

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``CreateEffectRequest``.

    Returns:
        A ``magic.effect_created`` Event.

    Raises:
        ValueError: If the character does not exist, is simplified, the
            effect type is invalid, or the cap is reached.
    """
    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    effect = effect_service_create(
        db,
        character_id=payload.character_id,
        name=payload.name,
        description=payload.description,
        effect_type=payload.effect_type,
        power_level=payload.power_level,
        charges_current=payload.charges_current,
        charges_max=payload.charges_max,
    )

    event = create_event(
        db,
        type="magic.effect_created",
        actor_type="gm",
        actor_id=user.id,
        changes={},
        created_objects=[{"type": "magic_effect", "id": effect.id}],
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "character",
                "target_id": payload.character_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# modify_effect handler
# ---------------------------------------------------------------------------


def handle_modify_effect(
    db: Session,
    user: User,
    payload: ModifyEffectRequest,
) -> Event:
    """Apply direct GM modifications to a Magic Effect and record an event.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``ModifyEffectRequest`` with ``effect_id`` and
            ``changes``.

    Returns:
        A ``magic.effect_charged`` (if only charges changed) or
        ``magic.effect_updated`` Event.

    Raises:
        ValueError: If the effect does not exist or visibility is invalid.
    """
    effect: MagicEffect | None = db.get(MagicEffect, payload.effect_id)
    if effect is None:
        raise ValueError(f"Magic effect '{payload.effect_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    changes: dict[str, Any] = {}
    ch = payload.changes
    has_charge_change = False

    # Name change.
    if ch.name is not None:
        before_name = effect.name
        effect.name = ch.name
        changes[f"magic_effect.{effect.id}.name"] = {
            "op": "field.set",
            "before": before_name,
            "after": ch.name,
        }

    # Description change.
    if ch.description is not None:
        before_desc = effect.description
        effect.description = ch.description
        changes[f"magic_effect.{effect.id}.description"] = {
            "op": "field.set",
            "before": before_desc,
            "after": ch.description,
        }

    # charges_current change.
    if ch.charges_current is not None:
        op_obj = ch.charges_current
        before_cc = effect.charges_current if effect.charges_current is not None else 0
        if op_obj.op == "delta":
            raw = before_cc + op_obj.value
        else:
            raw = op_obj.value
        new_cc = max(0, raw)
        effect.charges_current = new_cc
        changes[f"magic_effect.{effect.id}.charges_current"] = {
            "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
            "before": before_cc,
            "after": new_cc,
        }
        has_charge_change = True

    # charges_max change.
    if ch.charges_max is not None:
        op_obj = ch.charges_max
        before_cm = effect.charges_max if effect.charges_max is not None else 0
        if op_obj.op == "delta":
            raw = before_cm + op_obj.value
        else:
            raw = op_obj.value
        new_cm = max(0, raw)
        effect.charges_max = new_cm
        changes[f"magic_effect.{effect.id}.charges_max"] = {
            "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
            "before": before_cm,
            "after": new_cm,
        }
        has_charge_change = True

    # power_level change.
    if ch.power_level is not None:
        op_obj = ch.power_level
        before_pl = effect.power_level
        if op_obj.op == "delta":
            raw = before_pl + op_obj.value
        else:
            raw = op_obj.value
        new_pl = max(1, min(5, raw))
        effect.power_level = new_pl
        changes[f"magic_effect.{effect.id}.power_level"] = {
            "op": "meter.delta" if op_obj.op == "delta" else "meter.set",
            "before": before_pl,
            "after": new_pl,
        }

    db.flush()

    # Choose event type.
    charge_only = has_charge_change and all(
        k.endswith(".charges_current") or k.endswith(".charges_max")
        for k in changes
    )
    event_type = "magic.effect_charged" if charge_only else "magic.effect_updated"

    event = create_event(
        db,
        type=event_type,
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "character",
                "target_id": effect.character_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# retire_effect handler
# ---------------------------------------------------------------------------


def handle_retire_effect(
    db: Session,
    user: User,
    payload: RetireEffectRequest,
) -> Event:
    """Retire a Magic Effect (set is_active = false) and record an event.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``RetireEffectRequest`` with ``effect_id``.

    Returns:
        A ``magic.effect_retired`` Event.

    Raises:
        ValueError: If the effect does not exist or visibility is invalid.
    """
    effect: MagicEffect | None = db.get(MagicEffect, payload.effect_id)
    if effect is None:
        raise ValueError(f"Magic effect '{payload.effect_id}' not found.")

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    before_active = effect.is_active
    effect.is_active = False
    db.flush()

    event = create_event(
        db,
        type="magic.effect_retired",
        actor_type="gm",
        actor_id=user.id,
        changes={
            f"magic_effect.{effect.id}.is_active": {
                "op": "field.set",
                "before": before_active,
                "after": False,
            }
        },
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "character",
                "target_id": effect.character_id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# award_xp handler
# ---------------------------------------------------------------------------

_MAGIC_STAT_LEVEL_MAX: int = 5


def handle_award_xp(
    db: Session,
    user: User,
    payload: AwardXpRequest,
) -> Event:
    """Award Magic Stat XP to a character and record an event.

    XP is applied to the specified magic stat.  When cumulative XP reaches
    5, the stat levels up: ``level += 1``, XP resets to 0 (no overflow
    carry — spec: "Magic Stat XP: Resets to 0 on level-up. No overflow
    carry.").  Multiple level-ups are processed if ``xp_amount`` warrants
    it.  Level is capped at 5.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user performing the action.
        payload: Validated ``AwardXpRequest``.

    Returns:
        A ``character.magic_stat_changed`` Event with all XP and level
        changes recorded.

    Raises:
        ValueError: If the character does not exist, is not full, the
            magic_stat name is invalid, or visibility is invalid.
    """
    character: Character | None = db.get(Character, payload.character_id)
    if character is None or character.is_deleted:
        raise ValueError(f"Character '{payload.character_id}' not found.")
    if character.detail_level != "full":
        raise ValueError(
            f"Character '{payload.character_id}' is simplified. "
            "XP can only be awarded to full (PC) characters."
        )

    if payload.magic_stat not in _VALID_MAGIC_STATS:
        raise ValueError(
            f"Invalid magic_stat '{payload.magic_stat}'. "
            f"Must be one of: {sorted(_VALID_MAGIC_STATS)}."
        )

    if payload.visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{payload.visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    stat_name = payload.magic_stat
    current_magic: dict[str, Any] = {
        k: dict(v) for k, v in (character.magic_stats or {}).items()
    }
    stat_block = dict(current_magic.get(stat_name, {"level": 0, "xp": 0}))

    before_xp: int = stat_block.get("xp", 0)
    before_level: int = stat_block.get("level", 0)

    # Apply XP and handle level-ups.
    new_xp = before_xp + payload.xp_amount
    new_level = before_level
    while new_xp >= 5 and new_level < _MAGIC_STAT_LEVEL_MAX:
        new_level += 1
        new_xp = 0  # No overflow carry per spec.

    # If already at max level, XP still resets on overflow attempts
    # but level doesn't increase.
    if new_level >= _MAGIC_STAT_LEVEL_MAX and new_xp >= 5:
        new_xp = 0

    stat_block["xp"] = new_xp
    stat_block["level"] = new_level
    current_magic[stat_name] = stat_block
    character.magic_stats = current_magic

    db.flush()

    changes: dict[str, Any] = {}
    changes[f"character.{character.id}.magic_stats.{stat_name}.xp"] = {
        "op": "meter.delta",
        "before": before_xp,
        "after": new_xp,
    }
    if new_level != before_level:
        changes[f"character.{character.id}.magic_stats.{stat_name}.level"] = {
            "op": "field.set",
            "before": before_level,
            "after": new_level,
        }

    event = create_event(
        db,
        type="character.magic_stat_changed",
        actor_type="gm",
        actor_id=user.id,
        changes=changes,
        narrative=payload.narrative,
        visibility=payload.visibility,
        targets=[
            {
                "target_type": "character",
                "target_id": character.id,
                "is_primary": True,
            }
        ],
    )

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def dispatch_gm_action(
    db: Session,
    user: User,
    action_type: str,
    payload: Any,
) -> Event:
    """Route a GM action to its type-specific handler.

    Args:
        db: Active SQLAlchemy session.
        user: The authenticated GM user.
        action_type: Discriminator string, e.g. ``"modify_character"``.
        payload: The validated request object for the action.

    Returns:
        The Event created by the handler.

    Raises:
        ValueError: If ``action_type`` is not registered.
    """
    handlers = {
        "modify_character": handle_modify_character,
        "modify_group": handle_modify_group,
        "modify_location": handle_modify_location,
        "modify_clock": handle_modify_clock,
        "create_bond": handle_create_bond,
        "modify_bond": handle_modify_bond,
        "retire_bond": handle_retire_bond,
        "create_trait": handle_create_trait,
        "modify_trait": handle_modify_trait,
        "retire_trait": handle_retire_trait,
        "create_effect": handle_create_effect,
        "modify_effect": handle_modify_effect,
        "retire_effect": handle_retire_effect,
        "award_xp": handle_award_xp,
    }
    handler = handlers.get(action_type)
    if handler is None:
        raise ValueError(f"Unknown action type: {action_type!r}.")
    return handler(db, user, payload)
