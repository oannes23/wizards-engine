"""Service layer for Bond operations.

Bonds connect Game Objects (Characters, Groups, and Locations) via the unified
``slots`` table.  This module owns all bond creation, validation, and query
logic.  No HTTP concerns live here — route handlers call these functions.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its first
argument.

Key decisions reflected here (see spec/domains/bonds.md):
- ``slot_type`` is auto-inferred from source type/detail_level + target type.
- ``bidirectional`` is auto-inferred from pairing type (GM may override).
- Source slot limits are hard-enforced; target limits produce a soft warning.
- Duplicate active bonds per (source, target) pair are prevented.
- PC bonds start with charges=5 (full charges, base max) and degradations=0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.slot import Slot
from wizards_engine.services.shared import GAME_OBJECT_MODEL_MAP

if TYPE_CHECKING:
    from wizards_engine.schemas.bond import BondDisplayResponse

__all__ = [
    "CreateBondResult",
    "ApplyStrainResult",
    "ApplyTraumaResult",
    "create_bond",
    "get_bonds_for_owner",
    "get_inbound_bonds",
    "get_traits_for_owner",
    "get_group_members",
    "build_bond_display",
    "get_bond",
    "apply_bond_strain",
    "restore_bond_charges",
    "reverse_degradation",
    "count_active_traumas",
    "apply_trauma",
    "fix_trauma",
    "get_bonds_display_for_entity",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard slot limits per slot_type.  None = unlimited.
_SLOT_LIMITS: dict[str, int | None] = {
    "pc_bond": 8,
    "npc_bond": 7,
    "group_relation": 7,
    "group_holding": None,
    "location_bond": None,
}

# Pairings that default to bidirectional.
# (source_type, target_type) — both orderings must be listed for symmetric check.
_BIDIRECTIONAL_PAIRINGS: frozenset[tuple[str, str]] = frozenset(
    {
        ("character", "character"),
        ("character", "group"),
        ("group", "character"),  # symmetry of Character↔Group
        ("group", "group"),
    }
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CreateBondResult:
    """Result of a bond creation call.

    Attributes:
        bond: The newly created and flushed :class:`~wizards_engine.models.slot.Slot`
            instance.
        warnings: Zero or more informational strings.  Non-empty when a soft
            limit was exceeded on the target side of a bidirectional bond.
    """

    bond: Slot
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_game_object(
    db: Session,
    object_type: str,
    object_id: str,
) -> Character | Group | Location | None:
    """Return the active (non-deleted) Game Object, or ``None``.

    Args:
        db: Active SQLAlchemy session.
        object_type: One of ``"character"``, ``"group"``, ``"location"``.
        object_id: ULID of the Game Object.

    Returns:
        The ORM instance if found and not soft-deleted, else ``None``.
    """
    from wizards_engine.services.shared import get_game_object  # noqa: PLC0415
    return get_game_object(db, object_type, object_id)


def _infer_slot_type(
    source_type: str,
    source_detail_level: str | None,
    target_type: str,
) -> str:
    """Infer the ``slot_type`` for a new bond from context.

    Rules (from spec/domains/bonds.md — Slot Type Auto-Inference):

    ============================  ==========  ================
    Owner                         Target      slot_type
    ============================  ==========  ================
    Character (full)              any         ``pc_bond``
    Character (simplified)        any         ``npc_bond``
    Group                         Group       ``group_relation``
    Group                         Location    ``group_holding``
    Location                      any         ``location_bond``
    ============================  ==========  ================

    Args:
        source_type: ``"character"``, ``"group"``, or ``"location"``.
        source_detail_level: ``"full"`` or ``"simplified"`` for characters;
            ``None`` for groups and locations.
        target_type: ``"character"``, ``"group"``, or ``"location"``.

    Returns:
        The inferred ``slot_type`` string.

    Raises:
        ValueError: If the combination is not recognised.
    """
    if source_type == "character":
        if source_detail_level == "full":
            return "pc_bond"
        return "npc_bond"

    if source_type == "group":
        if target_type == "location":
            return "group_holding"
        if target_type == "group":
            return "group_relation"
        # Group → Character is not a canonical bond type per the spec.
        raise ValueError(
            f"Groups cannot create bonds to targets of type '{target_type}'. "
            "Groups support bonds to other Groups (group_relation) or "
            "Locations (group_holding) only."
        )

    if source_type == "location":
        return "location_bond"

    raise ValueError(f"Unknown source type: '{source_type}'")


def _infer_bidirectional(source_type: str, target_type: str) -> bool:
    """Return the default ``bidirectional`` value for a bond pairing.

    Character↔Character, Character↔Group, and Group↔Group default to
    bidirectional.  All Location-involved bonds default to directional.

    Args:
        source_type: ``"character"``, ``"group"``, or ``"location"``.
        target_type: ``"character"``, ``"group"``, or ``"location"``.

    Returns:
        ``True`` for bidirectional pairings, ``False`` for directional.
    """
    return (source_type, target_type) in _BIDIRECTIONAL_PAIRINGS


def _count_active_bonds(db: Session, owner_type: str, owner_id: str, slot_type: str) -> int:
    """Count active bonds of a given ``slot_type`` for a Game Object.

    Args:
        db: Active SQLAlchemy session.
        owner_type: ``"character"``, ``"group"``, or ``"location"``.
        owner_id: ULID of the owning Game Object.
        slot_type: Bond slot type to count.

    Returns:
        Integer count of active bonds.
    """
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == owner_type,
            Slot.owner_id == owner_id,
            Slot.slot_type == slot_type,
            Slot.is_active.is_(True),
        )
    )
    return len(db.execute(stmt).scalars().all())


def _count_inbound_active_bonds(
    db: Session,
    target_type: str,
    target_id: str,
) -> int:
    """Count active bidirectional bonds targeting a Game Object.

    Used for soft-limit checking on the target side.  Only bidirectional bonds
    count here because directional bonds do not "consume" a target slot.
    All bond slot types are counted regardless of origin — a PC bonding to an
    NPC still counts against the NPC's apparent capacity.

    Args:
        db: Active SQLAlchemy session.
        target_type: ``"character"``, ``"group"``, or ``"location"``.
        target_id: ULID of the target Game Object.

    Returns:
        Integer count of active bidirectional inbound bonds.
    """
    stmt = select(Slot).where(
        and_(
            Slot.target_type == target_type,
            Slot.target_id == target_id,
            Slot.is_active.is_(True),
            Slot.bidirectional.is_(True),
        )
    )
    return len(db.execute(stmt).scalars().all())


def _has_active_bond(
    db: Session,
    owner_type: str,
    owner_id: str,
    target_type: str,
    target_id: str,
) -> bool:
    """Return ``True`` if an active bond from source to target already exists.

    Checks all slot types to prevent any duplicate active bond per
    (source, target) pair.

    Args:
        db: Active SQLAlchemy session.
        owner_type: Source Game Object type.
        owner_id: Source Game Object ULID.
        target_type: Target Game Object type.
        target_id: Target Game Object ULID.

    Returns:
        ``True`` if at least one active bond exists for this pairing.
    """
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == owner_type,
            Slot.owner_id == owner_id,
            Slot.target_type == target_type,
            Slot.target_id == target_id,
            Slot.is_active.is_(True),
        )
    )
    return db.execute(stmt).scalars().first() is not None


def _target_soft_limit(target_type: str, target: Character | Group | Location) -> int | None:
    """Return the soft slot limit for the given target Game Object.

    The soft limit reflects how many bonds (outbound + inbound bidirectional)
    a target is expected to have before the GM receives a warning.  ``None``
    means no limit applies (Locations and Group Holdings are unlimited).

    Args:
        target_type: ``"character"``, ``"group"``, or ``"location"``.
        target: The resolved ORM instance.

    Returns:
        Integer limit, or ``None`` if no soft limit applies.
    """
    if target_type == "character":
        detail_level = getattr(target, "detail_level", None)
        return 8 if detail_level == "full" else 7
    if target_type == "group":
        # Group→Group relations are limited to 7.  Holdings are unlimited, but
        # holdings are directional so they never reach this code path.
        return 7
    # Locations have unlimited bonds — no soft limit.
    return None


def _count_all_active_outbound_bonds(
    db: Session,
    owner_type: str,
    owner_id: str,
) -> int:
    """Count all active bond-type slots owned by a Game Object.

    Used together with inbound count for effective bond total at the target.

    Args:
        db: Active SQLAlchemy session.
        owner_type: ``"character"``, ``"group"``, or ``"location"``.
        owner_id: ULID of the owning Game Object.

    Returns:
        Integer count of active bonds of any bond slot_type.
    """
    bond_types = [
        "pc_bond",
        "npc_bond",
        "group_relation",
        "group_holding",
        "location_bond",
    ]
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == owner_type,
            Slot.owner_id == owner_id,
            Slot.slot_type.in_(bond_types),
            Slot.is_active.is_(True),
        )
    )
    return len(db.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_bond(
    db: Session,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    source_label: str = "",
    target_label: str = "",
    description: str = "",
    bidirectional: bool | None = None,
) -> CreateBondResult:
    """Create a bond between two Game Objects.

    Validates source and target existence, infers ``slot_type`` and
    ``bidirectional`` default, enforces source hard slot limits, checks
    target soft limits, and prevents duplicate active bonds.

    PC bonds (``pc_bond``) are initialised with ``charges = 5`` (full charges)
    and ``degradations = 0``.

    Args:
        db: Active SQLAlchemy session.
        source_type: ``"character"``, ``"group"``, or ``"location"``.
        source_id: ULID of the source Game Object.
        target_type: ``"character"``, ``"group"``, or ``"location"``.
        target_id: ULID of the target Game Object.
        source_label: Optional label from the source's perspective.
        target_label: Optional label from the target's perspective (for
            bidirectional bonds).
        description: Optional freeform context.
        bidirectional: Override the auto-inferred bidirectionality.  ``None``
            triggers automatic inference from the pairing type.

    Returns:
        A :class:`CreateBondResult` containing the new bond and any warnings.

    Raises:
        ValueError: If source or target does not exist, if the source has
            reached its hard slot limit, if a duplicate active bond exists,
            or if the (source_type, target_type) pairing is invalid.
    """
    # -- Validate source -------------------------------------------------------
    source = _get_game_object(db, source_type, source_id)
    if source is None:
        raise ValueError(
            f"Source {source_type} '{source_id}' not found or has been deleted."
        )

    # -- Self-bond guard -------------------------------------------------------
    if source_type == target_type and source_id == target_id:
        raise ValueError("A Game Object cannot have a bond to itself.")

    # -- Validate target -------------------------------------------------------
    target = _get_game_object(db, target_type, target_id)
    if target is None:
        raise ValueError(
            f"Target {target_type} '{target_id}' not found or has been deleted."
        )

    # -- Infer slot_type -------------------------------------------------------
    source_detail_level: str | None = getattr(source, "detail_level", None)
    slot_type = _infer_slot_type(source_type, source_detail_level, target_type)

    # -- Infer / apply bidirectionality ----------------------------------------
    if bidirectional is None:
        bidirectional = _infer_bidirectional(source_type, target_type)

    # -- Duplicate active bond check -------------------------------------------
    if _has_active_bond(db, source_type, source_id, target_type, target_id):
        raise ValueError(
            f"An active bond from {source_type} '{source_id}' to "
            f"{target_type} '{target_id}' already exists. "
            "Retire or replace the existing bond before creating a new one."
        )

    # -- Source hard slot limit ------------------------------------------------
    limit = _SLOT_LIMITS.get(slot_type)
    if limit is not None:
        current_count = _count_active_bonds(db, source_type, source_id, slot_type)
        if current_count >= limit:
            raise ValueError(
                f"{source_type.capitalize()} '{source_id}' already has "
                f"{current_count} active {slot_type} bonds (limit: {limit}). "
                "Retire an existing bond before adding a new one."
            )

    # -- Build bond slot -------------------------------------------------------
    bond_name = source_label or (target_label or "")

    slot_kwargs: dict = {
        "slot_type": slot_type,
        "owner_type": source_type,
        "owner_id": source_id,
        "target_type": target_type,
        "target_id": target_id,
        "name": bond_name,
        "description": description or None,
        "source_label": source_label or None,
        "target_label": target_label or None,
        "bidirectional": bidirectional,
        "is_active": True,
    }

    # PC bonds get mechanical fields initialised.
    if slot_type == "pc_bond":
        slot_kwargs["charges"] = 5  # Full charges (base max)
        slot_kwargs["degradations"] = 0
        slot_kwargs["is_trauma"] = False

    bond = Slot(**slot_kwargs)
    db.add(bond)
    db.flush()
    db.refresh(bond)

    # -- Target soft limit check (bidirectional only) -------------------------
    warnings: list[str] = []
    if bidirectional:
        soft_limit = _target_soft_limit(target_type, target)
        if soft_limit is not None:
            # Effective bond count = bonds the target owns + all bidirectional
            # bonds pointing to the target (from any owner type).
            inbound = _count_inbound_active_bonds(db, target_type, target_id)
            owned = _count_all_active_outbound_bonds(db, target_type, target_id)
            total_effective = inbound + owned
            # The new bond was flushed above and is already included in the
            # inbound count.  If total > limit, we are over capacity.
            if total_effective > soft_limit:
                warnings.append(
                    f"Target {target_type} '{target_id}' now has "
                    f"{total_effective} effective bonds "
                    f"(soft limit: {soft_limit}). "
                    "Bond was created, but the target is over their slot capacity."
                )

    return CreateBondResult(bond=bond, warnings=warnings)


def get_bonds_for_owner(
    db: Session,
    owner_type: str,
    owner_id: str,
    include_inactive: bool = False,
) -> list[Slot]:
    """Return all bonds owned by a Game Object.

    Fetches all bond-type slots (``pc_bond``, ``npc_bond``, ``group_relation``,
    ``group_holding``, ``location_bond``) for the given owner.  Only active
    bonds are returned by default.

    Args:
        db: Active SQLAlchemy session.
        owner_type: ``"character"``, ``"group"``, or ``"location"``.
        owner_id: ULID of the owning Game Object.
        include_inactive: When ``True``, retired/past bonds are also included.

    Returns:
        Ordered list of :class:`~wizards_engine.models.slot.Slot` instances,
        sorted by creation time (ascending).
    """
    bond_types = [
        "pc_bond",
        "npc_bond",
        "group_relation",
        "group_holding",
        "location_bond",
    ]
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == owner_type,
            Slot.owner_id == owner_id,
            Slot.slot_type.in_(bond_types),
        )
    )
    if not include_inactive:
        stmt = stmt.where(Slot.is_active.is_(True))

    stmt = stmt.order_by(Slot.created_at)
    return list(db.execute(stmt).scalars().all())


def get_inbound_bonds(
    db: Session,
    target_type: str,
    target_id: str,
    include_inactive: bool = False,
) -> list[Slot]:
    """Return all bidirectional bonds whose target is the given Game Object.

    These are bonds owned by *other* Game Objects that point back to this
    entity.  Only bidirectional bonds appear here, since directional bonds
    are not visible from the target's perspective.

    Args:
        db: Active SQLAlchemy session.
        target_type: ``"character"``, ``"group"``, or ``"location"``.
        target_id: ULID of the target Game Object.
        include_inactive: When ``True``, retired bonds are also included.

    Returns:
        Ordered list of :class:`~wizards_engine.models.slot.Slot` instances,
        sorted by creation time (ascending).
    """
    stmt = select(Slot).where(
        and_(
            Slot.target_type == target_type,
            Slot.target_id == target_id,
            Slot.bidirectional.is_(True),
        )
    )
    if not include_inactive:
        stmt = stmt.where(Slot.is_active.is_(True))

    stmt = stmt.order_by(Slot.created_at)
    return list(db.execute(stmt).scalars().all())


def get_traits_for_owner(
    db: Session,
    owner_type: str,
    owner_id: str,
    slot_type: str,
) -> list[Slot]:
    """Return all active trait slots of a given type for a Game Object.

    Used to fetch descriptive traits for Groups (``group_trait``) and
    Locations (``feature_trait``).  Only active traits are returned; retired
    traits are excluded.

    Args:
        db: Active SQLAlchemy session.
        owner_type: ``"character"``, ``"group"``, or ``"location"``.
        owner_id: ULID of the owning Game Object.
        slot_type: The trait slot type to filter by (e.g. ``"group_trait"``
            or ``"feature_trait"``).

    Returns:
        Ordered list of :class:`~wizards_engine.models.slot.Slot` instances,
        sorted by creation time (ascending).
    """
    stmt = (
        select(Slot)
        .where(
            and_(
                Slot.owner_type == owner_type,
                Slot.owner_id == owner_id,
                Slot.slot_type == slot_type,
                Slot.is_active.is_(True),
            )
        )
        .order_by(Slot.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def get_group_members(
    db: Session,
    group_id: str,
) -> list[Character]:
    """Return all Characters with an active bond targeting the given Group.

    Derived membership — a Character's bond to a Group IS their membership.
    Both PCs (``pc_bond``) and NPCs (``npc_bond``) are included.  Only
    active bonds are considered; retired bonds do not confer membership.

    Args:
        db: Active SQLAlchemy session.
        group_id: ULID of the Group.

    Returns:
        List of :class:`~wizards_engine.models.character.Character` instances
        sorted by name (ascending).
    """
    stmt = select(Slot).where(
        and_(
            Slot.target_type == "group",
            Slot.target_id == group_id,
            Slot.slot_type.in_(["pc_bond", "npc_bond"]),
            Slot.is_active.is_(True),
        )
    )
    member_slots = list(db.execute(stmt).scalars().all())

    if not member_slots:
        return []

    owner_ids = list({slot.owner_id for slot in member_slots})
    char_stmt = (
        select(Character)
        .where(Character.id.in_(owner_ids))
        .order_by(Character.name)
    )
    return list(db.execute(char_stmt).scalars().all())


def _resolve_name(
    db: Session,
    object_type: str,
    object_id: str,
) -> str:
    """Return the display name for any Game Object, or a fallback string.

    Args:
        db: Active SQLAlchemy session.
        object_type: ``"character"``, ``"group"``, or ``"location"``.
        object_id: ULID of the Game Object.

    Returns:
        The object's name, or ``"[deleted]"`` if not found.
    """
    model = GAME_OBJECT_MODEL_MAP.get(object_type)
    if model is None:
        return "[unknown]"
    obj = db.get(model, object_id)
    if obj is None:
        return "[deleted]"
    return obj.name  # type: ignore[attr-defined]


def build_bond_display(
    db: Session,
    bond: Slot,
    viewer_type: str,
    viewer_id: str,
) -> "BondDisplayResponse":
    """Convert a Slot instance to a perspective-normalized BondDisplayResponse.

    The viewer determines which label and "other end" are presented:

    - **Outbound bond** (viewer is the bond owner): ``label = source_label``,
      ``target_*`` fields describe the actual target.
    - **Inbound bidirectional bond** (viewer is the bond target): the viewer
      is looking *from the target side*, so ``label = target_label`` and
      ``target_*`` fields describe the bond owner (the other party).

    Args:
        db: Active SQLAlchemy session.
        bond: The Slot representing a bond.
        viewer_type: Type of the entity whose perspective we are normalizing
            (``"character"``, ``"group"``, or ``"location"``).
        viewer_id: ULID of the viewing entity.

    Returns:
        A :class:`~wizards_engine.schemas.bond.BondDisplayResponse` instance.
    """
    from wizards_engine.schemas.bond import BondDisplayResponse  # noqa: PLC0415

    is_inbound = bond.owner_type != viewer_type or bond.owner_id != viewer_id

    if is_inbound:
        # Viewer is the TARGET — show the bond owner as "the other end".
        other_type = bond.owner_type
        other_id = bond.owner_id
        label = bond.target_label or ""
    else:
        # Viewer is the SOURCE — show the actual target as "the other end".
        other_type = bond.target_type or ""
        other_id = bond.target_id or ""
        label = bond.source_label or ""

    target_name = _resolve_name(db, other_type, other_id) if other_id else ""

    # Compute effective_charges_max for PC bonds.
    effective_charges_max = None
    if bond.slot_type == "pc_bond" and bond.degradations is not None:
        effective_charges_max = 5 - bond.degradations

    return BondDisplayResponse(
        id=bond.id,
        slot_type=bond.slot_type,
        target_type=other_type,
        target_id=other_id,
        target_name=target_name,
        label=label,
        description=bond.description,
        is_active=bond.is_active,
        bidirectional=bool(bond.bidirectional),
        charges=bond.charges,
        degradations=bond.degradations,
        is_trauma=bond.is_trauma,
        effective_charges_max=effective_charges_max,
    )


# ---------------------------------------------------------------------------
# PC bond charge mechanics
# ---------------------------------------------------------------------------


def get_bond(db: Session, bond_id: str) -> Slot | None:
    """Return the Slot with the given ID, or ``None`` if it does not exist.

    Args:
        db: Active SQLAlchemy session.
        bond_id: ULID of the slot/bond to retrieve.

    Returns:
        The :class:`~wizards_engine.models.slot.Slot` instance, or ``None``.
    """
    return db.get(Slot, bond_id)


@dataclass
class ApplyStrainResult:
    """Result of an :func:`apply_bond_strain` call.

    Attributes:
        bond: The updated :class:`~wizards_engine.models.slot.Slot` instance.
        degraded: ``True`` when the strain caused the bond's charges to reach
            zero and a degradation was applied.
    """

    bond: Slot
    degraded: bool


def _validate_pc_bond(bond: Slot | None, bond_id: str) -> Slot:
    """Validate that *bond* exists and is an active, non-trauma pc_bond.

    Args:
        bond: The Slot to validate (may be ``None`` if not found).
        bond_id: The ULID used in the lookup (for error messages).

    Returns:
        The validated bond.

    Raises:
        ValueError: If the bond does not exist, is not a ``pc_bond``, is
            inactive, or is a trauma bond.
    """
    if bond is None:
        raise ValueError(f"Bond '{bond_id}' not found.")
    if bond.slot_type != "pc_bond":
        raise ValueError(
            f"Bond '{bond_id}' is a '{bond.slot_type}', not a 'pc_bond'. "
            "Charge mechanics apply to PC bonds only."
        )
    if not bond.is_active:
        raise ValueError(
            f"Bond '{bond_id}' is inactive. Charge mechanics require an active bond."
        )
    if bond.is_trauma:
        raise ValueError(
            f"Bond '{bond_id}' is a trauma bond. Charge mechanics do not apply to "
            "trauma bonds."
        )
    return bond


def apply_bond_strain(db: Session, bond_id: str) -> ApplyStrainResult:
    """Apply one strain to a PC bond (lose one charge).

    Decrements the bond's charge count by 1.  If the charge reaches 0 after
    decrement, a degradation is applied in the same operation:
    ``degradations`` increments by 1 and charges reset to the new effective
    maximum (``5 - degradations``).

    The effective maximum BEFORE this call is ``5 - degradations``.
    After degradation it becomes ``5 - (degradations + 1)``.

    Args:
        db: Active SQLAlchemy session.
        bond_id: ULID of the PC bond to strain.

    Returns:
        An :class:`ApplyStrainResult` with the updated bond and a flag
        indicating whether a degradation occurred.

    Raises:
        ValueError: If the bond does not exist, is not an active pc_bond, or
            is a trauma bond.
    """
    bond = _validate_pc_bond(db.get(Slot, bond_id), bond_id)

    bond.charges -= 1

    degraded = False
    if bond.charges <= 0:
        # Charges depleted — apply degradation in the same operation.
        bond.charges = 0  # clamp (shouldn't go below 0 in practice)
        bond.degradations = (bond.degradations or 0) + 1
        new_effective_max = 5 - bond.degradations
        # Reset charges to the new effective max (may be 0 if at 5 degradations).
        bond.charges = max(0, new_effective_max)
        degraded = True

    db.flush()
    db.refresh(bond)
    return ApplyStrainResult(bond=bond, degraded=degraded)


def restore_bond_charges(db: Session, bond_id: str) -> Slot:
    """Restore a PC bond's charges to its effective maximum (Maintain Bond).

    Sets ``charges`` to ``5 - degradations``.  This is the service
    implementation of the *Maintain Bond* downtime action.

    Args:
        db: Active SQLAlchemy session.
        bond_id: ULID of the PC bond to restore.

    Returns:
        The updated :class:`~wizards_engine.models.slot.Slot`.

    Raises:
        ValueError: If the bond does not exist, is not an active pc_bond, or
            is a trauma bond.
    """
    bond = _validate_pc_bond(db.get(Slot, bond_id), bond_id)

    effective_max = 5 - (bond.degradations or 0)
    bond.charges = max(0, effective_max)

    db.flush()
    db.refresh(bond)
    return bond


def reverse_degradation(db: Session, bond_id: str) -> Slot:
    """Decrement a PC bond's degradation count by 1 (GM action).

    ``degradations`` is decremented to a minimum of 0.  Charges are NOT
    automatically adjusted — the GM may follow up with
    :func:`restore_bond_charges` if desired.

    Args:
        db: Active SQLAlchemy session.
        bond_id: ULID of the PC bond to repair.

    Returns:
        The updated :class:`~wizards_engine.models.slot.Slot`.

    Raises:
        ValueError: If the bond does not exist, is not an active pc_bond, or
            is a trauma bond.
    """
    bond = _validate_pc_bond(db.get(Slot, bond_id), bond_id)

    current_degradations = bond.degradations or 0
    bond.degradations = max(0, current_degradations - 1)

    db.flush()
    db.refresh(bond)
    return bond


def count_active_traumas(db: Session, character_id: str) -> int:
    """Return the count of active trauma bonds for a character.

    Trauma bonds are active ``pc_bond`` slots with ``is_trauma = True``.
    This count drives the ``effective_stress_max`` formula:
    ``9 - count_active_traumas(db, character_id)``.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the character.

    Returns:
        Integer count of active trauma bonds.
    """
    stmt = select(Slot).where(
        and_(
            Slot.owner_type == "character",
            Slot.owner_id == character_id,
            Slot.slot_type == "pc_bond",
            Slot.is_trauma.is_(True),
            Slot.is_active.is_(True),
        )
    )
    return len(db.execute(stmt).scalars().all())


@dataclass
class ApplyTraumaResult:
    """Result of an :func:`apply_trauma` call.

    Attributes:
        retired_bond: The original bond that was retired to Past.
        trauma_bond: The newly created trauma bond.
        character: The updated character (stress reset to 0).
    """

    retired_bond: Slot
    trauma_bond: Slot
    character: "Character"


def apply_trauma(
    db: Session,
    character_id: str,
    retire_bond_id: str,
    trauma_name: str,
    trauma_description: str,
) -> ApplyTraumaResult:
    """Apply a Trauma to a character as a compound operation.

    Retires the specified bond to Past, creates a new trauma bond in its place,
    and resets the character's stress to 0.  All mutations are issued in a
    single :func:`~sqlalchemy.orm.Session.flush` call.

    The compound operation mirrors the spec: "retire bond + create trauma bond +
    reset stress" are treated as one atomic change (see bonds.md — Trauma, and
    character-core.md — Stress Range and Consequences).

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the full (PC) character receiving the Trauma.
        retire_bond_id: ULID of the active, non-trauma ``pc_bond`` to retire.
        trauma_name: Name for the new trauma bond.
        trauma_description: Description for the new trauma bond.

    Returns:
        An :class:`ApplyTraumaResult` containing the retired bond, the new
        trauma bond, and the updated character.

    Raises:
        ValueError: If the character does not exist, is simplified, if the
            bond is not found, is not a ``pc_bond``, is not owned by this
            character, is already inactive, or is already a trauma bond.
    """
    from wizards_engine.models.character import Character  # noqa: PLC0415

    # -- Validate character ---------------------------------------------------
    character = db.get(Character, character_id)
    if character is None:
        raise ValueError(f"Character '{character_id}' not found.")
    if character.detail_level != "full":
        raise ValueError(
            f"Character '{character_id}' is simplified (NPC). "
            "Trauma applies to full (PC) characters only."
        )

    # -- Validate the bond to retire -----------------------------------------
    bond = db.get(Slot, retire_bond_id)
    if bond is None:
        raise ValueError(f"Bond '{retire_bond_id}' not found.")
    if bond.slot_type != "pc_bond":
        raise ValueError(
            f"Bond '{retire_bond_id}' is a '{bond.slot_type}', not a 'pc_bond'. "
            "Only PC bonds can be retired for Trauma."
        )
    if bond.owner_type != "character" or bond.owner_id != character_id:
        raise ValueError(
            f"Bond '{retire_bond_id}' is not owned by character '{character_id}'."
        )
    if not bond.is_active:
        raise ValueError(
            f"Bond '{retire_bond_id}' is already inactive. "
            "Only active bonds can be retired for Trauma."
        )
    if bond.is_trauma:
        raise ValueError(
            f"Bond '{retire_bond_id}' is already a trauma bond. "
            "Cannot retire a trauma bond as a Trauma target."
        )

    # -- Compound operation: retire bond, create trauma, reset stress --------
    # Step 1: Retire the chosen bond.
    bond.is_active = False

    # Step 2: Create the trauma bond in its place.
    trauma_bond = Slot(
        slot_type="pc_bond",
        owner_type="character",
        owner_id=character_id,
        target_type=None,
        target_id=None,
        name=trauma_name,
        description=trauma_description,
        is_active=True,
        bidirectional=False,
        is_trauma=True,
        charges=5,
        degradations=0,
    )
    db.add(trauma_bond)

    # Step 3: Reset character stress.
    character.stress = 0

    # Flush all three mutations in one operation.
    db.flush()
    db.refresh(bond)
    db.refresh(trauma_bond)
    db.refresh(character)

    return ApplyTraumaResult(
        retired_bond=bond,
        trauma_bond=trauma_bond,
        character=character,
    )


def fix_trauma(db: Session, trauma_bond_id: str) -> Slot:
    """Retire an active trauma bond (GM action — fixing a Trauma).

    Marks the trauma bond as inactive (``is_active = False``).  The GM
    decides what comes next — a blank slot, a new bond, etc. — via separate
    calls.  No automatic restoration of the original bond.

    Args:
        db: Active SQLAlchemy session.
        trauma_bond_id: ULID of the active trauma bond to retire.

    Returns:
        The retired :class:`~wizards_engine.models.slot.Slot` instance.

    Raises:
        ValueError: If the bond is not found, is not a trauma bond, or is
            already inactive.
    """
    bond = db.get(Slot, trauma_bond_id)
    if bond is None:
        raise ValueError(f"Bond '{trauma_bond_id}' not found.")
    if not bond.is_trauma:
        raise ValueError(
            f"Bond '{trauma_bond_id}' is not a trauma bond. "
            "fix_trauma only operates on trauma bonds (is_trauma=True)."
        )
    if not bond.is_active:
        raise ValueError(
            f"Bond '{trauma_bond_id}' is already inactive."
        )

    bond.is_active = False
    db.flush()
    db.refresh(bond)
    return bond


def get_bonds_display_for_entity(
    db: Session,
    entity_type: str,
    entity_id: str,
    owned_only: bool = False,
) -> dict[str, list["BondDisplayResponse"]]:
    """Return bonds for a Game Object, grouped by active/past status.

    By default merges outbound bonds and inbound bidirectional bonds into a
    single list, normalized to the viewer's perspective.  When
    ``owned_only=True``, only bonds where the entity is the owner are
    returned — inbound bidirectional bonds are excluded.

    Returns a dict with two keys:

    - ``"active"``: current bonds (``is_active = True``).
    - ``"past"``: retired bonds (``is_active = False``).

    Perspective normalization is applied via :func:`build_bond_display`.

    Args:
        db: Active SQLAlchemy session.
        entity_type: ``"character"``, ``"group"``, or ``"location"``.
        entity_id: ULID of the Game Object.
        owned_only: When ``True``, skip inbound bond query and return only
            bonds where the entity is the owner.  Defaults to ``False``.

    Returns:
        Dict with ``"active"`` and ``"past"`` lists of
        :class:`~wizards_engine.schemas.bond.BondDisplayResponse`.
    """
    owned = get_bonds_for_owner(db, entity_type, entity_id, include_inactive=True)

    if owned_only:
        all_bonds: list[Slot] = owned
    else:
        inbound = get_inbound_bonds(db, entity_type, entity_id, include_inactive=True)

        # Merge and deduplicate by bond ID.
        seen: set[str] = set()
        all_bonds = []
        for bond in owned + inbound:
            if bond.id not in seen:
                seen.add(bond.id)
                all_bonds.append(bond)

    active: list[BondDisplayResponse] = []
    past: list[BondDisplayResponse] = []

    for bond in all_bonds:
        display = build_bond_display(db, bond, entity_type, entity_id)
        if bond.is_active:
            active.append(display)
        else:
            past.append(display)

    return {"active": active, "past": past}
