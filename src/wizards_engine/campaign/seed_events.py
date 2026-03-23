"""Post-import event and proposal seeding script (Story 8.7.2).

Generates realistic events and proposals via the internal service layer
so that every UI feature has data to display after a fresh import.

The script is idempotent — it checks whether events already exist in the
database before writing anything.  Running it multiple times on the same
database is safe.

Event coverage
--------------
- character.stress_changed, character.free_time_changed,
  character.plot_changed, character.gnosis_changed
- character.skills_changed, character.magic_stats_changed
- character.resolve_trauma_generated (rider event)
- bond.created, bond.degraded, bond.retired
- trait.created, trait.recharged, trait.retired
- effect.created, effect.used, effect.retired
- clock.advanced, clock.completed
- session.started, session.ended
- proposal.submitted, proposal.approved, proposal.rejected
- gm_action.modify_character, gm_action.create_bond, gm_action.modify_bond,
  gm_action.create_trait, gm_action.award_xp, gm_action.modify_clock

Proposal states covered
-----------------------
- 2 pending (1 player origin, 1 system origin)
- 3 approved
- 2 rejected

Visibility levels covered
-------------------------
All 7 levels: silent, gm_only, private, bonded, familiar, public, global

Usage (via CLI)
---------------
    uv run wizards-campaign seed-events [--db-url sqlite:///path/to/db]
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.event import Event
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.session import Session as SessionModel, SessionParticipant
from wizards_engine.models.slot import Slot
from wizards_engine.models.user import User
from wizards_engine.services.event import create_event


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def seed_events(db: Session) -> SeedResult:
    """Generate realistic events and proposals against an imported database.

    Checks for existing events first — returns early without writing anything
    if the database already contains events (idempotent).

    Args:
        db: Active SQLAlchemy session.  The caller is responsible for
            committing the transaction on success.

    Returns:
        A :class:`SeedResult` summarising what was created.

    Raises:
        RuntimeError: If required entities (characters, users) are not found
            in the database.  Run ``wizards-campaign import`` first.
    """
    # Idempotency guard — do nothing if events already exist.
    existing_count = db.execute(select(Event)).first()
    if existing_count is not None:
        return SeedResult(skipped=True, reason="Events already exist in the database.")

    # Resolve entities we'll reference throughout.
    ctx = _resolve_context(db)

    result = SeedResult()

    # 1. Seed session states.
    _seed_sessions(db, ctx, result)

    # 2. Seed events (all major types, varied visibility, targets, rider).
    _seed_events(db, ctx, result)

    # 3. Seed proposals in all states.
    _seed_proposals(db, ctx, result)

    db.flush()
    return result


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class SeedResult:
    """Summary of what the seeding script created.

    Attributes
    ----------
    skipped:
        ``True`` if seeding was skipped because events already existed.
    reason:
        Human-readable explanation when ``skipped`` is ``True``.
    events_created:
        Number of Event rows written.
    proposals_created:
        Number of Proposal rows written.
    sessions_created:
        Number of Session rows written.
    """

    def __init__(
        self,
        *,
        skipped: bool = False,
        reason: str = "",
    ) -> None:
        self.skipped = skipped
        self.reason = reason
        self.events_created: int = 0
        self.proposals_created: int = 0
        self.sessions_created: int = 0


# ---------------------------------------------------------------------------
# Context resolution
# ---------------------------------------------------------------------------


class _SeedContext:
    """Holds entity references resolved at the start of seeding."""

    def __init__(self) -> None:
        self.gm: User | None = None
        self.players: list[User] = []
        self.pcs: list[Character] = []
        self.npcs: list[Character] = []
        self.groups: list[Group] = []
        self.locations: list[Location] = []
        self.clocks: list[Clock] = []
        # Sessions we create (not imported sessions).
        self.draft_session: SessionModel | None = None
        self.active_session: SessionModel | None = None
        self.ended_sessions: list[SessionModel] = []


def _resolve_context(db: Session) -> _SeedContext:
    """Load and validate entities from the database.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        A populated :class:`_SeedContext`.

    Raises:
        RuntimeError: If the database has no characters or users (import
            has not been run).
    """
    ctx = _SeedContext()

    # Users.
    all_users = db.scalars(select(User)).all()
    ctx.gm = next((u for u in all_users if u.role == "gm"), None)
    ctx.players = [u for u in all_users if u.role == "player"]

    if not all_users:
        raise RuntimeError(
            "No users found. Run 'wizards-campaign import' before seeding."
        )

    # Characters — split into PCs (full) and NPCs (simplified).
    all_chars = db.scalars(
        select(Character).where(Character.is_deleted == False)  # noqa: E712
    ).all()
    ctx.pcs = [c for c in all_chars if c.detail_level == "full"]
    ctx.npcs = [c for c in all_chars if c.detail_level == "simplified"]

    if not ctx.pcs:
        raise RuntimeError(
            "No full (PC) characters found. Run 'wizards-campaign import' first."
        )

    # Groups, locations, clocks.
    ctx.groups = db.scalars(
        select(Group).where(Group.is_deleted == False)  # noqa: E712
    ).all()
    ctx.locations = db.scalars(
        select(Location).where(Location.is_deleted == False)  # noqa: E712
    ).all()
    ctx.clocks = db.scalars(
        select(Clock).where(Clock.is_deleted == False)  # noqa: E712
    ).all()

    return ctx


# ---------------------------------------------------------------------------
# Session seeding
# ---------------------------------------------------------------------------


def _seed_sessions(
    db: Session,
    ctx: _SeedContext,
    result: SeedResult,
) -> None:
    """Create 1 draft session, 1 active session, and 2 ended sessions.

    The active session has participants so that subsequent event creation
    can tag events to it via automatic session capture.

    Args:
        db: Active SQLAlchemy session.
        ctx: Entity context.
        result: Mutable result accumulator.
    """
    import datetime as _dt

    today = _dt.date.today()

    # --- Two ended sessions (past play dates). ---
    ended1 = SessionModel(
        status="ended",
        time_now=10,
        date=today - _dt.timedelta(days=28),
        summary="The party discovered the hidden passage beneath the Keeper's sanctuary.",
        notes="Good session. Players engaged with the mystery well.",
    )
    db.add(ended1)
    db.flush()

    ended2 = SessionModel(
        status="ended",
        time_now=20,
        date=today - _dt.timedelta(days=14),
        summary="Confrontation at the ford. Theron's bond with the Scattered Chorus was tested.",
        notes="Combat ran long. Consider streamlining next time.",
    )
    db.add(ended2)
    db.flush()

    # Attach participants to ended sessions.
    for char in ctx.pcs[:3]:
        db.add(SessionParticipant(
            session_id=ended1.id,
            character_id=char.id,
            additional_contribution=False,
        ))
    db.flush()

    for char in ctx.pcs:
        db.add(SessionParticipant(
            session_id=ended2.id,
            character_id=char.id,
            additional_contribution=False,
        ))
    db.flush()

    ctx.ended_sessions = [ended1, ended2]
    result.sessions_created += 2

    # --- Active session (current play date). ---
    active = SessionModel(
        status="active",
        time_now=30,
        date=today,
        summary=None,
        notes="In progress.",
    )
    db.add(active)
    db.flush()

    # Attach all PCs to the active session.
    for char in ctx.pcs:
        db.add(SessionParticipant(
            session_id=active.id,
            character_id=char.id,
            additional_contribution=False,
        ))
    db.flush()

    ctx.active_session = active
    result.sessions_created += 1

    # --- Draft session (scheduled, not yet started). ---
    draft = SessionModel(
        status="draft",
        time_now=40,
        date=today + _dt.timedelta(days=14),
        summary=None,
        notes="Planned: travel to Argos and meet with Drakos.",
    )
    db.add(draft)
    db.flush()

    ctx.draft_session = draft
    result.sessions_created += 1


# ---------------------------------------------------------------------------
# Event seeding
# ---------------------------------------------------------------------------


def _make_targets(
    *entries: tuple[str, str, bool],
) -> list[dict[str, Any]]:
    """Build a targets list from (target_type, target_id, is_primary) tuples.

    Args:
        entries: Variable positional tuples of (target_type, target_id, is_primary).

    Returns:
        A list of target dicts suitable for :func:`create_event`.
    """
    return [
        {"target_type": tt, "target_id": tid, "is_primary": primary}
        for tt, tid, primary in entries
    ]


def _seed_events(
    db: Session,
    ctx: _SeedContext,
    result: SeedResult,
) -> None:
    """Create one event of every major type with varied visibility, actors, and targets.

    Events are spread across both ended sessions and the active session.

    Args:
        db: Active SQLAlchemy session.
        ctx: Entity context.
        result: Mutable result accumulator.
    """
    pc0 = ctx.pcs[0]
    pc1 = ctx.pcs[1] if len(ctx.pcs) > 1 else ctx.pcs[0]
    gm_id = ctx.gm.id if ctx.gm else None
    player_id = ctx.players[0].id if ctx.players else None
    ended1 = ctx.ended_sessions[0]
    ended2 = ctx.ended_sessions[1]
    active = ctx.active_session

    # -------------------------------------------------------------------
    # Session events (system actor, global visibility)
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="session.started",
        actor_type="system",
        actor_id=None,
        changes={f"session.{ended1.id}.status": {"op": "field.set", "before": "draft", "after": "active"}},
        narrative="Session started.",
        visibility="global",
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="session.ft_distributed",
        actor_type="system",
        actor_id=None,
        changes={f"character.{pc0.id}.free_time": {"op": "meter.delta", "before": 3, "after": 8}},
        visibility="silent",
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="session.plot_distributed",
        actor_type="system",
        actor_id=None,
        changes={f"character.{pc0.id}.plot": {"op": "meter.delta", "before": 1, "after": 2}},
        visibility="silent",
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="session.ended",
        actor_type="system",
        actor_id=None,
        changes={f"session.{ended1.id}.status": {"op": "field.set", "before": "active", "after": "ended"}},
        narrative="Session ended.",
        visibility="global",
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="session.started",
        actor_type="system",
        actor_id=None,
        changes={f"session.{ended2.id}.status": {"op": "field.set", "before": "draft", "after": "active"}},
        narrative="Session started.",
        visibility="global",
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="session.ended",
        actor_type="system",
        actor_id=None,
        changes={f"session.{ended2.id}.status": {"op": "field.set", "before": "active", "after": "ended"}},
        narrative="Session ended.",
        visibility="global",
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="session.started",
        actor_type="system",
        actor_id=None,
        changes={f"session.{active.id}.status": {"op": "field.set", "before": "draft", "after": "active"}},
        narrative="Session started.",
        visibility="global",
        session_id=active.id,
    ))

    # -------------------------------------------------------------------
    # character.* events — varied visibility, targeting characters
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="character.stress_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.stress": {"op": "meter.delta", "before": 2, "after": 5}},
        narrative=f"{pc0.name} took a blow during the chase.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="character.stress_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc1.id}.stress": {"op": "meter.set", "before": 7, "after": 3}},
        narrative=f"{pc1.name} recovered after resting at the sanctuary.",
        visibility="public",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="character.free_time_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.free_time": {"op": "meter.delta", "before": 8, "after": 6}},
        narrative=f"{pc0.name} spent free time on research.",
        visibility="private",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="character.plot_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc1.id}.plot": {"op": "meter.delta", "before": 1, "after": 3}},
        narrative=f"{pc1.name} acted decisively and gained narrative influence.",
        visibility="public",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="character.gnosis_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.gnosis": {"op": "meter.delta", "before": 4, "after": 7}},
        narrative=f"{pc0.name} attuned to the ley confluence at the ford.",
        visibility="bonded",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="character.skills_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc1.id}.skills.awareness": {"op": "field.set", "before": 2, "after": 3}},
        narrative=f"{pc1.name}'s perception sharpened through practice.",
        visibility="gm_only",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="character.magic_stats_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.magic_stats.wyrding.xp": {"op": "meter.delta", "before": 1, "after": 3}},
        narrative=f"{pc0.name} advanced in wyrding craft.",
        visibility="familiar",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    # -------------------------------------------------------------------
    # bond.* events
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="bond.created",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        created_objects=[{"type": "slot", "slot_type": "pc_bond", "owner_id": pc0.id}],
        narrative=f"A bond formed between {pc0.name} and a new ally encountered at the ford.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="bond.degraded",
        actor_type="system",
        actor_id=None,
        changes={},
        narrative=f"A bond held by {pc1.name} degraded after repeated strain.",
        visibility="bonded",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="bond.retired",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        deleted_objects=[{"type": "slot", "slot_type": "pc_bond"}],
        narrative=f"An old bond of {pc0.name} was retired — the relationship dissolved.",
        visibility="private",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    # -------------------------------------------------------------------
    # trait.* events
    # -------------------------------------------------------------------

    # Find a trait slot to reference.
    trait_slot = db.scalars(
        select(Slot).where(
            Slot.owner_id == pc0.id,
            Slot.slot_type.in_(["core_trait", "role_trait"]),
            Slot.is_active == True,  # noqa: E712
        )
    ).first()

    trait_name = trait_slot.name if trait_slot else "Iron Resolve"
    trait_slot_id = trait_slot.id if trait_slot else "unknown"

    _emit(db, result, create_event(
        db,
        type="trait.created",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        created_objects=[{"type": "slot", "id": trait_slot_id, "name": trait_name}],
        narrative=f"'{trait_name}' trait assigned to {pc0.name}.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="trait.recharged",
        actor_type="player",
        actor_id=player_id,
        changes={f"slot.{trait_slot_id}.charge": {"op": "meter.delta", "before": 2, "after": 5}},
        narrative=f"{pc0.name} recharged '{trait_name}' during downtime.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="trait.retired",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        deleted_objects=[{"type": "slot", "slot_type": "role_trait"}],
        narrative=f"A role trait was retired as part of {pc1.name}'s character evolution.",
        visibility="gm_only",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended2.id,
    ))

    # -------------------------------------------------------------------
    # effect.* events
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="effect.created",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        created_objects=[{"type": "magic_effect"}],
        narrative=f"A new magical effect took hold on {pc0.name}.",
        visibility="familiar",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="effect.used",
        actor_type="player",
        actor_id=player_id,
        changes={},
        narrative=f"{pc0.name} invoked a magic effect during the confrontation.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="effect.retired",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        deleted_objects=[{"type": "magic_effect"}],
        narrative=f"A temporary effect on {pc1.name} expired.",
        visibility="gm_only",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended2.id,
    ))

    # -------------------------------------------------------------------
    # clock.* events — target a clock and a group
    # -------------------------------------------------------------------

    clock_targets: list[dict[str, Any]] = []
    clock_changes: dict[str, Any] = {}

    if ctx.clocks:
        clock = ctx.clocks[0]
        clock_targets = _make_targets(("clock", clock.id, True))
        clock_changes = {
            f"clock.{clock.id}.progress": {"op": "meter.delta", "before": 2, "after": 4}
        }

    group_targets: list[dict[str, Any]] = []
    if ctx.groups:
        group = ctx.groups[0]
        group_targets = _make_targets(("group", group.id, True))

    _emit(db, result, create_event(
        db,
        type="clock.advanced",
        actor_type="gm",
        actor_id=gm_id,
        changes=clock_changes,
        narrative="The Iron Compact's consolidation effort advanced another step.",
        visibility="public",
        targets=clock_targets or group_targets,
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="clock.completed",
        actor_type="system",
        actor_id=None,
        changes={},
        narrative="A clock reached completion — consequences are imminent.",
        visibility="global",
        targets=group_targets,
        session_id=ended2.id,
    ))

    # -------------------------------------------------------------------
    # proposal.submitted / approved / rejected events
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="proposal.submitted",
        actor_type="player",
        actor_id=player_id,
        changes={},
        narrative=f"{pc0.name} submitted a proposal to use a skill in a high-stakes moment.",
        visibility="private",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="proposal.approved",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.stress": {"op": "meter.delta", "before": 4, "after": 2}},
        narrative="GM approved: the action succeeded, stress reduced as a reward.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="proposal.rejected",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        narrative="GM rejected: insufficient resources at this time.",
        visibility="private",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended1.id,
    ))

    # -------------------------------------------------------------------
    # gm_action.* events — multiple GM action types
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="gm_action.modify_character",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.stress": {"op": "meter.set", "before": 3, "after": 1}},
        narrative="GM directly adjusted stress after a major narrative beat.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="gm_action.create_bond",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        created_objects=[{"type": "slot", "slot_type": "npc_bond"}],
        narrative=f"GM created a bond for an NPC connecting them to {pc0.name}.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="gm_action.modify_bond",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        narrative="GM modified a bond's charges following a major story moment.",
        visibility="public",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended2.id,
    ))

    _emit(db, result, create_event(
        db,
        type="gm_action.create_trait",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        created_objects=[{"type": "slot", "slot_type": "core_trait"}],
        narrative=f"GM awarded a new core trait to {pc1.name}.",
        visibility="public",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=ended1.id,
    ))

    _emit(db, result, create_event(
        db,
        type="gm_action.award_xp",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.magic_stats.being.xp": {"op": "meter.delta", "before": 0, "after": 2}},
        narrative=f"{pc0.name} gained magic XP for exceptional roleplay.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=ended1.id,
    ))

    if ctx.clocks:
        clock = ctx.clocks[0]
        _emit(db, result, create_event(
            db,
            type="gm_action.modify_clock",
            actor_type="gm",
            actor_id=gm_id,
            changes={f"clock.{clock.id}.progress": {"op": "meter.delta", "before": 0, "after": 2}},
            narrative="GM advanced the clock following narrative developments.",
            visibility="public",
            targets=_make_targets(("clock", clock.id, True)),
            session_id=ended1.id,
        ))

    # -------------------------------------------------------------------
    # Events targeting groups and locations
    # -------------------------------------------------------------------

    if ctx.groups:
        grp = ctx.groups[0]
        _emit(db, result, create_event(
            db,
            type="gm_action.modify_group",
            actor_type="gm",
            actor_id=gm_id,
            changes={f"group.{grp.id}.tier": {"op": "field.set", "before": 2, "after": 3}},
            narrative=f"The {grp.name} grew in power and influence.",
            visibility="global",
            targets=_make_targets(("group", grp.id, True)),
            session_id=ended2.id,
        ))

    if ctx.locations:
        loc = ctx.locations[0]
        _emit(db, result, create_event(
            db,
            type="gm_action.modify_location",
            actor_type="gm",
            actor_id=gm_id,
            changes={},
            narrative=f"The {loc.name} was re-classified in the world map.",
            visibility="public",
            targets=_make_targets(("location", loc.id, True)),
            session_id=ended2.id,
        ))

    # -------------------------------------------------------------------
    # Active-session events (will auto-capture the active session)
    # -------------------------------------------------------------------

    _emit(db, result, create_event(
        db,
        type="character.stress_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.stress": {"op": "meter.delta", "before": 1, "after": 4}},
        narrative=f"{pc0.name} faced a sudden ambush.",
        visibility="public",
        targets=_make_targets(("character", pc0.id, True)),
        session_id=active.id,
    ))

    # -------------------------------------------------------------------
    # Rider event (parent_event_id populated) — resolve_trauma generated
    # -------------------------------------------------------------------
    stress_event = create_event(
        db,
        type="character.stress_changed",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc1.id}.stress": {"op": "meter.set", "before": 5, "after": 8}},
        narrative=f"{pc1.name} was overwhelmed — stress near the limit.",
        visibility="public",
        targets=_make_targets(("character", pc1.id, True)),
        session_id=active.id,
    )
    result.events_created += 1

    rider = create_event(
        db,
        type="character.resolve_trauma_generated",
        actor_type="system",
        actor_id=None,
        changes={},
        visibility="silent",
        parent_event_id=stress_event.id,
        targets=_make_targets(("character", pc1.id, True)),
    )
    result.events_created += 1

    # -------------------------------------------------------------------
    # Events with remaining visibility levels not yet covered
    # -------------------------------------------------------------------

    # "silent" — already covered by resolve_trauma_generated rider above.
    # "gm_only" — already covered by skills_changed.
    # "private" — already covered by bond.retired.
    # "bonded" — already covered by gnosis_changed.
    # "familiar" — already covered by magic_stats_changed.
    # "public" — covered throughout.
    # "global" — covered by session events.

    # One more: group target with public visibility in ended2.
    if ctx.groups and len(ctx.groups) > 1:
        grp2 = ctx.groups[1]
        _emit(db, result, create_event(
            db,
            type="bond.created",
            actor_type="gm",
            actor_id=gm_id,
            changes={},
            narrative=f"A new bond formed connecting a PC to {grp2.name}.",
            visibility="public",
            targets=[
                _make_targets(("character", pc0.id, True))[0],
                _make_targets(("group", grp2.id, False))[0],
            ],
            session_id=ended2.id,
        ))


def _emit(db: Session, result: SeedResult, event: Event) -> None:
    """Record that an event was emitted and increment the counter.

    Args:
        db: Active SQLAlchemy session (unused here but kept for symmetry).
        result: Mutable result accumulator.
        event: The event that was just created.
    """
    result.events_created += 1


# ---------------------------------------------------------------------------
# Proposal seeding
# ---------------------------------------------------------------------------


def _seed_proposals(
    db: Session,
    ctx: _SeedContext,
    result: SeedResult,
) -> None:
    """Create proposals in pending, approved, and rejected states.

    Coverage:
    - 2 pending: 1 player-origin (use_skill), 1 system-origin (resolve_clock)
    - 3 approved: use_magic, rest, new_trait
    - 2 rejected: work_on_project, new_bond

    Args:
        db: Active SQLAlchemy session.
        ctx: Entity context.
        result: Mutable result accumulator.
    """
    pc0 = ctx.pcs[0]
    pc1 = ctx.pcs[1] if len(ctx.pcs) > 1 else ctx.pcs[0]
    gm_id = ctx.gm.id if ctx.gm else None
    ended1 = ctx.ended_sessions[0]
    ended2 = ctx.ended_sessions[1]
    active = ctx.active_session

    # -------------------------------------------------------------------
    # 1 pending — player-origin, use_skill
    # -------------------------------------------------------------------
    pending_player = Proposal(
        character_id=pc0.id,
        action_type="use_skill",
        origin="player",
        narrative=(
            f"{pc0.name} wants to use Awareness to detect an ambush before "
            "the group crosses the next ford."
        ),
        selections={
            "skill": "awareness",
            "plot_spend": 0,
            "modifier_trait_ids": [],
            "modifier_bond_ids": [],
        },
        calculated_effect={"outcome": "pending_gm_review"},
        status="pending",
        gm_notes=None,
    )
    db.add(pending_player)
    db.flush()
    result.proposals_created += 1

    create_event(
        db,
        type="proposal.submitted",
        actor_type="player",
        actor_id=ctx.players[0].id if ctx.players else None,
        changes={},
        narrative="Skill use proposal submitted.",
        visibility="private",
        proposal_id=pending_player.id,
        targets=[{"target_type": "character", "target_id": pc0.id, "is_primary": True}],
        session_id=active.id,
    )
    result.events_created += 1

    # -------------------------------------------------------------------
    # 1 pending — system-origin, resolve_clock
    # -------------------------------------------------------------------
    clock_id: str | None = ctx.clocks[0].id if ctx.clocks else None
    pending_system = Proposal(
        character_id=None,
        action_type="resolve_clock",
        origin="system",
        narrative="",
        selections={},
        calculated_effect=None,
        status="pending",
        gm_notes=None,
        clock_id=clock_id,
    )
    db.add(pending_system)
    db.flush()
    result.proposals_created += 1

    create_event(
        db,
        type="proposal.submitted",
        actor_type="system",
        actor_id=None,
        changes={},
        narrative="System generated resolve_clock proposal on clock completion.",
        visibility="gm_only",
        proposal_id=pending_system.id,
        targets=(
            [{"target_type": "clock", "target_id": clock_id, "is_primary": True}]
            if clock_id else []
        ),
        session_id=ended2.id,
    )
    result.events_created += 1

    # -------------------------------------------------------------------
    # 3 approved proposals
    # -------------------------------------------------------------------

    # Approved: use_magic
    approved_magic = Proposal(
        character_id=pc0.id,
        action_type="use_magic",
        origin="player",
        narrative=(
            f"{pc0.name} channeled wyrding to obscure the group's passage through "
            "hostile territory."
        ),
        selections={"stat": "wyrding", "plot_spend": 1, "modifier_trait_ids": [], "modifier_bond_ids": []},
        calculated_effect={"stress_cost": 1, "gnosis_gain": 2},
        status="approved",
        gm_notes="Approved. The mist held long enough to pass unseen.",
        gm_overrides={},
    )
    db.add(approved_magic)
    db.flush()
    result.proposals_created += 1

    approved_magic_event = create_event(
        db,
        type="proposal.approved",
        actor_type="gm",
        actor_id=gm_id,
        changes={
            f"character.{pc0.id}.stress": {"op": "meter.delta", "before": 3, "after": 4},
            f"character.{pc0.id}.gnosis": {"op": "meter.delta", "before": 4, "after": 6},
        },
        narrative="Magic use approved — the group slipped through unseen.",
        visibility="public",
        proposal_id=approved_magic.id,
        targets=[{"target_type": "character", "target_id": pc0.id, "is_primary": True}],
        session_id=ended2.id,
    )
    result.events_created += 1
    approved_magic.event_id = approved_magic_event.id
    db.flush()

    # Approved: rest
    approved_rest = Proposal(
        character_id=pc1.id,
        action_type="rest",
        origin="player",
        narrative=f"{pc1.name} spent downtime recovering — long sleep and minimal obligations.",
        selections={"free_time_spend": 1, "modifier_trait_ids": [], "modifier_bond_ids": []},
        calculated_effect={"stress_reduction": 3},
        status="approved",
        gm_notes="Approved. Quiet downtime — stress reduced.",
        gm_overrides={},
    )
    db.add(approved_rest)
    db.flush()
    result.proposals_created += 1

    approved_rest_event = create_event(
        db,
        type="proposal.approved",
        actor_type="gm",
        actor_id=gm_id,
        changes={
            f"character.{pc1.id}.stress": {"op": "meter.delta", "before": 6, "after": 3},
            f"character.{pc1.id}.free_time": {"op": "meter.delta", "before": 8, "after": 7},
        },
        narrative="Rest approved — significant stress recovery.",
        visibility="private",
        proposal_id=approved_rest.id,
        targets=[{"target_type": "character", "target_id": pc1.id, "is_primary": True}],
        session_id=ended1.id,
    )
    result.events_created += 1
    approved_rest.event_id = approved_rest_event.id
    db.flush()

    # Approved: new_trait
    approved_trait = Proposal(
        character_id=pc0.id,
        action_type="new_trait",
        origin="player",
        narrative=(
            f"{pc0.name} proposes a new role trait: 'Poisoner's Patience' — the ability "
            "to wait and observe before striking with precision."
        ),
        selections={"trait_name": "Poisoner's Patience", "free_time_spend": 2, "modifier_bond_ids": []},
        calculated_effect={"slot_type": "role_trait", "name": "Poisoner's Patience"},
        status="approved",
        gm_notes="Good fit for the character arc. Approved.",
        gm_overrides={},
    )
    db.add(approved_trait)
    db.flush()
    result.proposals_created += 1

    approved_trait_event = create_event(
        db,
        type="proposal.approved",
        actor_type="gm",
        actor_id=gm_id,
        changes={f"character.{pc0.id}.free_time": {"op": "meter.delta", "before": 6, "after": 4}},
        created_objects=[{"type": "slot", "slot_type": "role_trait", "name": "Poisoner's Patience"}],
        narrative="New trait approved — 'Poisoner's Patience' added to character sheet.",
        visibility="public",
        proposal_id=approved_trait.id,
        targets=[{"target_type": "character", "target_id": pc0.id, "is_primary": True}],
        session_id=ended1.id,
    )
    result.events_created += 1
    approved_trait.event_id = approved_trait_event.id
    db.flush()

    # -------------------------------------------------------------------
    # 2 rejected proposals
    # -------------------------------------------------------------------

    # Rejected: work_on_project
    rejected_project = Proposal(
        character_id=pc1.id,
        action_type="work_on_project",
        origin="player",
        narrative=(
            f"{pc1.name} wants to spend downtime advancing the resistance network's "
            "counter-intelligence capabilities."
        ),
        selections={"clock_id": clock_id or "", "free_time_spend": 2, "modifier_bond_ids": []},
        calculated_effect={"clock_advance": 2},
        status="rejected",
        gm_notes="Rejected — the clock is currently under a narrative hold. Try again next session.",
        gm_overrides={},
    )
    db.add(rejected_project)
    db.flush()
    result.proposals_created += 1

    create_event(
        db,
        type="proposal.rejected",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        narrative="Project work rejected — narrative hold on this clock.",
        visibility="private",
        proposal_id=rejected_project.id,
        targets=[{"target_type": "character", "target_id": pc1.id, "is_primary": True}],
        session_id=ended1.id,
    )
    result.events_created += 1

    # Rejected: new_bond
    rejected_bond = Proposal(
        character_id=pc0.id,
        action_type="new_bond",
        origin="player",
        narrative=(
            f"{pc0.name} wants to formalize the bond with Myrtos — acknowledging that "
            "the adversarial relationship has become something more complicated."
        ),
        selections={
            "target_type": "character",
            "target_name": "Myrtos",
            "free_time_spend": 1,
            "modifier_bond_ids": [],
        },
        calculated_effect={"bond_type": "pc_bond"},
        status="rejected",
        gm_notes=(
            "Not yet — the Myrtos arc isn't ready to crystallize. "
            "Hold this proposal for a better narrative moment."
        ),
        gm_overrides={},
    )
    db.add(rejected_bond)
    db.flush()
    result.proposals_created += 1

    create_event(
        db,
        type="proposal.rejected",
        actor_type="gm",
        actor_id=gm_id,
        changes={},
        narrative="New bond rejected — arc timing not right yet.",
        visibility="private",
        proposal_id=rejected_bond.id,
        targets=[{"target_type": "character", "target_id": pc0.id, "is_primary": True}],
        session_id=ended2.id,
    )
    result.events_created += 1
