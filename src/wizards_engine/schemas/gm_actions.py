"""Pydantic schemas for POST /api/v1/gm/actions — GM direct action requests.

Each action type has its own request model.  The top-level
``GmActionRequest`` is a discriminated union dispatched on ``action_type``.

Implemented action types:
- ``modify_character``: Directly mutate a character's meters, skills,
  magic stats, attributes, or last_session_time_now.
- ``modify_group``: Set the tier field on a Group.
- ``modify_location``: Re-parent a Location (change parent_id).
- ``modify_clock``: Advance or set clock progress; auto-generates
  a ``resolve_clock`` proposal on completion.
- ``create_bond``: Create a bond between two Game Objects.
- ``modify_bond``: Change bond stress, labels, or description.
- ``retire_bond``: Deactivate a bond (set is_active = false).
- ``create_trait``: Assign a trait (template-linked or freeform) to an owner.
- ``modify_trait``: Change charges, name, or description on a trait.
- ``retire_trait``: Deactivate a trait (set is_active = false).
- ``create_effect``: Create a Magic Effect on a character.
- ``modify_effect``: Change power_level, charges, or description on an effect.
- ``retire_effect``: Deactivate a Magic Effect (set is_active = false).
- ``award_xp``: Award Magic Stat XP to a character, with level-up handling.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------


class MeterChange(BaseModel):
    """A single meter change operation.

    Attributes
    ----------
    op:
        ``"delta"`` applies a relative offset; ``"set"`` assigns an
        absolute value.
    value:
        The numeric operand — positive or negative for delta, absolute
        for set.
    """

    op: Literal["delta", "set"]
    value: int


# ---------------------------------------------------------------------------
# modify_character
# ---------------------------------------------------------------------------


class MagicStatChange(BaseModel):
    """Changes to a single magic stat within the ``magic_stats`` JSON block.

    Attributes
    ----------
    xp:
        XP to add (delta only — always additive).  Optional.
    level:
        Absolute level to set.  Optional.
    """

    xp: int | None = None
    level: int | None = None


class ModifyCharacterChanges(BaseModel):
    """The ``changes`` sub-object for a ``modify_character`` action.

    All fields are optional — only include the fields you want to modify.

    Attributes
    ----------
    stress:
        Delta or set operation on the character's stress meter (0–9).
    free_time:
        Delta or set operation on the character's free-time meter (0–20).
    plot:
        Delta or set operation on the character's plot meter (>=0).
    gnosis:
        Delta or set operation on the character's gnosis meter (0–23).
    skills:
        Map of ``{skill_name: level}`` to set individual skills (0–3).
    magic_stats:
        Map of ``{stat_name: MagicStatChange}`` for XP addition or
        level assignment on individual magic stats (level 0–5, xp 0–4).
    attributes:
        Key-value pairs merged into the character's ``attributes`` JSON
        blob.  Existing keys not mentioned here are preserved.
    last_session_time_now:
        Absolute value to set for ``last_session_time_now``.
    """

    stress: MeterChange | None = None
    free_time: MeterChange | None = None
    plot: MeterChange | None = None
    gnosis: MeterChange | None = None
    skills: dict[str, int] | None = None
    magic_stats: dict[str, MagicStatChange] | None = None
    attributes: dict[str, Any] | None = None
    last_session_time_now: int | None = None


class ModifyCharacterRequest(BaseModel):
    """Request body for the ``modify_character`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_character"`` — used for dispatcher routing.
    target_id:
        ULID of the character to modify.
    changes:
        The set of changes to apply.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"gm_only"`` (character changes are GM-only by default).
    """

    action_type: Literal["modify_character"]
    target_id: str
    changes: ModifyCharacterChanges
    narrative: str | None = None
    visibility: str = "gm_only"


# ---------------------------------------------------------------------------
# modify_group
# ---------------------------------------------------------------------------


class ModifyGroupChanges(BaseModel):
    """The ``changes`` sub-object for a ``modify_group`` action.

    Attributes
    ----------
    tier:
        Absolute tier value to set on the Group.  Must be a non-negative
        integer.
    """

    tier: int = Field(..., ge=0)


class ModifyGroupRequest(BaseModel):
    """Request body for the ``modify_group`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_group"`` — used for dispatcher routing.
    target_id:
        ULID of the Group to modify.
    changes:
        The set of changes to apply.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to ``"public"``.
    """

    action_type: Literal["modify_group"]
    target_id: str
    changes: ModifyGroupChanges
    narrative: str | None = None
    visibility: str = "public"


# ---------------------------------------------------------------------------
# modify_location
# ---------------------------------------------------------------------------


class ModifyLocationChanges(BaseModel):
    """The ``changes`` sub-object for a ``modify_location`` action.

    Attributes
    ----------
    parent_id:
        ULID of the new parent Location, or ``None`` to make the location a
        root node.  When provided the referenced Location must exist and must
        not create a circular hierarchy.
    """

    parent_id: str | None


class ModifyLocationRequest(BaseModel):
    """Request body for the ``modify_location`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_location"`` — used for dispatcher routing.
    target_id:
        ULID of the Location to re-parent.
    changes:
        The set of changes to apply.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to ``"public"``.
    """

    action_type: Literal["modify_location"]
    target_id: str
    changes: ModifyLocationChanges
    narrative: str | None = None
    visibility: str = "public"


# ---------------------------------------------------------------------------
# modify_clock
# ---------------------------------------------------------------------------


class ModifyClockAnnotationMetadata(BaseModel):
    """Optional annotation metadata stored on the clock event.

    Attributes
    ----------
    notes:
        Free-text annotation note.
    related_events:
        List of event IDs related to this clock advance.
    related_objects:
        List of ``{type, id}`` dicts for related game objects.
    """

    notes: str | None = None
    related_events: list[str] | None = None
    related_objects: list[dict[str, Any]] | None = None


class ModifyClockChanges(BaseModel):
    """The ``changes`` sub-object for a ``modify_clock`` action.

    Attributes
    ----------
    progress:
        Delta or set operation on the clock's progress counter.
        Progress is clamped to ``>= 0``; there is no upper hard cap
        (the GM may advance past ``segments``).
    """

    progress: MeterChange


class ModifyClockRequest(BaseModel):
    """Request body for the ``modify_clock`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_clock"`` — used for dispatcher routing.
    target_id:
        ULID of the Clock to advance.
    changes:
        The progress change to apply.
    metadata:
        Optional annotation metadata stored on the generated event.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to ``"public"``.
    """

    action_type: Literal["modify_clock"]
    target_id: str
    changes: ModifyClockChanges
    metadata: ModifyClockAnnotationMetadata | None = None
    narrative: str | None = None
    visibility: str = "public"


# ---------------------------------------------------------------------------
# create_bond
# ---------------------------------------------------------------------------


class CreateBondRequest(BaseModel):
    """Request body for the ``create_bond`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"create_bond"``.
    owner_type:
        Type of the bond source: ``"character"``, ``"group"``, or
        ``"location"``.
    owner_id:
        ULID of the source Game Object.
    target_type:
        Type of the bond target: ``"character"``, ``"group"``, or
        ``"location"``.
    target_id:
        ULID of the target Game Object.
    source_label:
        Optional label from the source's perspective.
    target_label:
        Optional label from the target's perspective (for bidirectional
        bonds).
    description:
        Optional freeform description.
    bidirectional:
        Override the auto-inferred bidirectionality.  ``None`` (omitted)
        triggers automatic inference.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["create_bond"]
    owner_type: str
    owner_id: str
    target_type: str
    target_id: str
    source_label: str | None = None
    target_label: str | None = None
    description: str | None = None
    bidirectional: bool | None = None
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# modify_bond
# ---------------------------------------------------------------------------


class ModifyBondChanges(BaseModel):
    """Changes sub-object for a ``modify_bond`` action.

    Attributes
    ----------
    source_label:
        Replacement label for the source's perspective.
    target_label:
        Replacement label for the target's perspective.
    description:
        Replacement description text.
    stress:
        Delta or set on the bond's charge count (``stress`` column).
    stress_degradations:
        Delta or set on the bond's degradation count
        (``stress_degradations`` column).
    """

    source_label: str | None = None
    target_label: str | None = None
    description: str | None = None
    stress: MeterChange | None = None
    stress_degradations: MeterChange | None = None


class ModifyBondRequest(BaseModel):
    """Request body for the ``modify_bond`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_bond"``.
    bond_id:
        ULID of the slot (bond) to modify.
    changes:
        Fields to change on the bond.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["modify_bond"]
    bond_id: str
    changes: ModifyBondChanges
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# retire_bond
# ---------------------------------------------------------------------------


class RetireBondRequest(BaseModel):
    """Request body for the ``retire_bond`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"retire_bond"``.
    bond_id:
        ULID of the slot (bond) to retire.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["retire_bond"]
    bond_id: str
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# create_trait
# ---------------------------------------------------------------------------


class CreateTraitRequest(BaseModel):
    """Request body for the ``create_trait`` GM action.

    Covers both template-linked PC traits (``core_trait``, ``role_trait``)
    and freeform group/location traits (``group_trait``, ``feature_trait``).

    Attributes
    ----------
    action_type:
        Always ``"create_trait"``.
    owner_type:
        Type of the trait owner: ``"character"``, ``"group"``, or
        ``"location"``.
    owner_id:
        ULID of the owning Game Object.
    slot_type:
        One of ``"core_trait"``, ``"role_trait"``, ``"group_trait"``,
        or ``"feature_trait"``.
    template_id:
        ULID of the TraitTemplate — required for ``core_trait`` and
        ``role_trait``.  Must be ``None`` for freeform traits.
    name:
        Freeform name — required for ``group_trait`` and
        ``feature_trait``.  Ignored for template-linked traits (name
        comes from the template).
    description:
        Freeform description — used for group/location traits; optional
        for template-linked traits.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["create_trait"]
    owner_type: str
    owner_id: str
    slot_type: str
    template_id: str | None = None
    name: str | None = None
    description: str | None = None
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# modify_trait
# ---------------------------------------------------------------------------


class ModifyTraitChanges(BaseModel):
    """Changes sub-object for a ``modify_trait`` action.

    Attributes
    ----------
    name:
        Replacement name (freeform traits only; PC traits get their name
        from the template).
    description:
        Replacement description.
    charge:
        Delta or set on the trait's charge counter.
    """

    name: str | None = None
    description: str | None = None
    charge: MeterChange | None = None


class ModifyTraitRequest(BaseModel):
    """Request body for the ``modify_trait`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_trait"``.
    trait_id:
        ULID of the slot (trait) to modify.
    changes:
        Fields to change on the trait.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["modify_trait"]
    trait_id: str
    changes: ModifyTraitChanges
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# retire_trait
# ---------------------------------------------------------------------------


class RetireTraitRequest(BaseModel):
    """Request body for the ``retire_trait`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"retire_trait"``.
    trait_id:
        ULID of the slot (trait) to retire.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["retire_trait"]
    trait_id: str
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# create_effect
# ---------------------------------------------------------------------------


class CreateEffectRequest(BaseModel):
    """Request body for the ``create_effect`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"create_effect"``.
    character_id:
        ULID of the full character receiving the effect.
    name:
        Effect name.
    description:
        Effect description.
    effect_type:
        One of ``"instant"``, ``"charged"``, or ``"permanent"``.
    power_level:
        Effect power level (1–5).
    charges_current:
        Current charges — required for ``"charged"`` effects; must be
        omitted for instant/permanent.
    charges_max:
        Maximum charges — required for ``"charged"`` effects; must be
        omitted for instant/permanent.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["create_effect"]
    character_id: str
    name: str
    description: str
    effect_type: str
    power_level: int
    charges_current: int | None = None
    charges_max: int | None = None
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# modify_effect
# ---------------------------------------------------------------------------


class ModifyEffectChanges(BaseModel):
    """Changes sub-object for a ``modify_effect`` action.

    Attributes
    ----------
    name:
        Replacement name.
    description:
        Replacement description.
    charges_current:
        Delta or set on ``charges_current``.
    charges_max:
        Delta or set on ``charges_max``.
    power_level:
        Delta or set on ``power_level``.
    """

    name: str | None = None
    description: str | None = None
    charges_current: MeterChange | None = None
    charges_max: MeterChange | None = None
    power_level: MeterChange | None = None


class ModifyEffectRequest(BaseModel):
    """Request body for the ``modify_effect`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"modify_effect"``.
    effect_id:
        ULID of the MagicEffect to modify.
    changes:
        Fields to change on the effect.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["modify_effect"]
    effect_id: str
    changes: ModifyEffectChanges
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# retire_effect
# ---------------------------------------------------------------------------


class RetireEffectRequest(BaseModel):
    """Request body for the ``retire_effect`` GM action.

    Attributes
    ----------
    action_type:
        Always ``"retire_effect"``.
    effect_id:
        ULID of the MagicEffect to retire.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"bonded"``.
    """

    action_type: Literal["retire_effect"]
    effect_id: str
    narrative: str | None = None
    visibility: str = "bonded"


# ---------------------------------------------------------------------------
# award_xp
# ---------------------------------------------------------------------------


class AwardXpRequest(BaseModel):
    """Request body for the ``award_xp`` GM action.

    XP is awarded to a single Magic Stat.  When cumulative XP reaches 5,
    the stat levels up (level += 1, XP resets to 0 — no overflow carry).
    Multiple level-ups are possible in one call if ``xp_amount`` is large
    enough (each 5 XP = one level).

    Attributes
    ----------
    action_type:
        Always ``"award_xp"``.
    character_id:
        ULID of the full character receiving XP.
    magic_stat:
        One of ``"being"``, ``"wyrding"``, ``"summoning"``,
        ``"enchanting"``, or ``"dreaming"``.
    xp_amount:
        Non-negative integer amount of XP to award.
    narrative:
        Optional human-readable description recorded on the event.
    visibility:
        Visibility level for the generated event.  Defaults to
        ``"private"`` (XP awards are between GM and player).
    """

    action_type: Literal["award_xp"]
    character_id: str
    magic_stat: str
    xp_amount: int = Field(..., ge=0)
    narrative: str | None = None
    visibility: str = "private"


# ---------------------------------------------------------------------------
# Top-level discriminated union
# ---------------------------------------------------------------------------

GmActionRequest = Annotated[
    Union[
        ModifyCharacterRequest,
        ModifyGroupRequest,
        ModifyLocationRequest,
        ModifyClockRequest,
        CreateBondRequest,
        ModifyBondRequest,
        RetireBondRequest,
        CreateTraitRequest,
        ModifyTraitRequest,
        RetireTraitRequest,
        CreateEffectRequest,
        ModifyEffectRequest,
        RetireEffectRequest,
        AwardXpRequest,
    ],
    Field(discriminator="action_type"),
]
