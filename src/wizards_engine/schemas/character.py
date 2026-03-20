"""Pydantic schemas for Character API endpoints.

Covers create, update, list-query, and response shapes for the
``/api/v1/characters`` resource.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from wizards_engine.schemas.bond import BondGroups


class CharacterTraitResponse(BaseModel):
    """A single Core or Role trait slot on a full character's sheet.

    Names and descriptions are resolved from the linked template when a
    ``template_id`` is set, so the client always receives the current
    template text.

    Attributes
    ----------
    id:
        ULID of the Slot record.
    slot_type:
        ``"core_trait"`` or ``"role_trait"``.
    name:
        Trait name — from the template if ``template_id`` is set, otherwise
        the slot's own ``name`` field.
    description:
        Trait description — from the template if ``template_id`` is set,
        otherwise the slot's own ``description`` field.
    charge:
        Current charge count (0–5).  ``None`` if not yet initialised.
    is_active:
        ``True`` for active traits; ``False`` for retired/past traits.
    template_id:
        ULID of the linked TraitTemplate, or ``None`` if no template.
    created_at:
        ISO 8601 UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    slot_type: str
    name: str
    description: str | None
    charge: int | None
    is_active: bool
    template_id: str | None
    created_at: datetime


class CharacterTraitGroups(BaseModel):
    """Active and past traits for a full character, returned in separate groups.

    Attributes
    ----------
    active:
        Currently active Core/Role traits.
    past:
        Retired/past Core/Role traits.
    """

    active: list[CharacterTraitResponse] = []
    past: list[CharacterTraitResponse] = []


class MagicEffectResponse(BaseModel):
    """A single magic effect on a character's sheet.

    Attributes
    ----------
    id:
        ULID of the MagicEffect record.
    name:
        Effect name.
    description:
        Effect description.
    effect_type:
        ``"instant"``, ``"charged"``, or ``"permanent"``.
    power_level:
        Power level (1–5).
    charges_current:
        Current charges (charged effects only; ``None`` for instant/permanent).
    charges_max:
        Maximum charges (charged effects only; ``None`` for instant/permanent).
    is_active:
        ``True`` for active effects; ``False`` for retired/past effects.
    created_at:
        ISO 8601 UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    effect_type: str
    power_level: int
    charges_current: int | None
    charges_max: int | None
    is_active: bool
    created_at: datetime


class MagicEffectGroups(BaseModel):
    """Active and past magic effects for a character, returned in separate groups.

    Attributes
    ----------
    active:
        Currently active magic effects.
    past:
        Retired/past magic effects.
    """

    active: list[MagicEffectResponse] = []
    past: list[MagicEffectResponse] = []


class EntityRef(BaseModel):
    """Lightweight reference to a Game Object returned in presence/location tiers.

    Attributes
    ----------
    id:
        ULID primary key of the referenced entity.
    name:
        Display name.
    type:
        Entity type — ``"character"``, ``"group"``, or ``"location"``.
    """

    id: str
    name: str
    type: str


class LocationTiers(BaseModel):
    """Bond-distance location tiers for a Character.

    Attributes
    ----------
    common:
        Locations directly bonded to this Character (1-hop).
    familiar:
        Locations reachable through one Character intermediary (2-hop).
    known:
        Locations reachable through two intermediaries (3-hop).
    """

    common: list[EntityRef] = []
    familiar: list[EntityRef] = []
    known: list[EntityRef] = []


class CreateCharacterRequest(BaseModel):
    """Request body for POST /api/v1/characters.

    Attributes
    ----------
    name:
        Required. Character name, 1–200 characters after whitespace stripping.
    description:
        Optional. Freeform background or concept text.
    notes:
        Optional. Freeform GM notes.
    attributes:
        Optional. Freeform JSON blob for NPC mechanical data (traits, stats, etc.).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str | None = None
    notes: str | None = None
    attributes: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty and at most 200 characters after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 200:
            raise ValueError("name must be 200 characters or fewer")
        return v


class UpdateCharacterRequest(BaseModel):
    """Request body for PATCH /api/v1/characters/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  Sending ``null`` for a nullable field clears it.

    Attributes
    ----------
    name:
        New character name.  Must be non-empty if provided.
    description:
        New description, or ``null`` to clear.
    notes:
        New notes, or ``null`` to clear.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    description: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Ensure name is non-empty and at most 200 characters if provided."""
        if v is not None and not v:
            raise ValueError("name must not be empty")
        if v is not None and len(v) > 200:
            raise ValueError("name must be 200 characters or fewer")
        return v


class CharacterResponse(BaseModel):
    """Response body for a single Character resource.

    Returned by POST (201), PATCH (200), and list endpoints (200).

    Attributes
    ----------
    id:
        ULID primary key.
    name:
        Character name.
    description:
        Optional background/concept text.
    detail_level:
        ``"full"`` (PC) or ``"simplified"`` (NPC).
    attributes:
        Optional freeform JSON blob.
    notes:
        Optional GM notes.
    is_deleted:
        Soft-delete flag.
    created_at:
        ISO 8601 UTC creation timestamp.
    updated_at:
        ISO 8601 UTC last-modified timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    detail_level: str
    attributes: dict[str, Any] | None
    notes: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class CharacterDetailResponse(CharacterResponse):
    """Extended response for GET /api/v1/characters/{id}.

    Adds bonds (active + past, perspective-normalized) and bond-distance
    location tiers computed on read from the bond graph.

    For full (PC) characters, also includes all mechanical sheet fields,
    computed values, session history, traits, and magic effects.

    Attributes
    ----------
    bonds:
        All bonds on this character — both outbound and inbound bidirectional
        — grouped by active/past status.  Labels are normalized to the
        character's perspective.
    locations:
        Bond-distance location tiers: ``common`` (1-hop), ``familiar``
        (2-hop), and ``known`` (3-hop).  Computed on read from the bond graph
        using the Character-intermediary traversal algorithm.

    Full-character-only fields (``None`` for simplified characters):

    stress:
        Current Stress meter value (0–9).
    free_time:
        Current Free Time resource (0–20).
    plot:
        Current Plot resource (0–5, may temporarily exceed).
    gnosis:
        Current Gnosis resource (0–23).
    skills:
        JSON dict of all 8 skills with their current levels.
    magic_stats:
        JSON dict of all 5 magic stats with level and xp.
    last_session_time_now:
        The ``time_now`` value of the character's last attended session.
        Used to compute Free Time gained at session start.
    effective_stress_max:
        Computed: ``9 - count(trauma bonds)``.  The actual upper bound for
        Stress given current Trauma bond count.
    active_magic_effects_count:
        Count of active charged + permanent effects (toward the cap of 9).
    active_trait_count:
        Count of filled Core + Role trait slots (out of a total 5).
    active_bond_count:
        Count of active pc_bond slots (out of a total 8).
    session_ids:
        Ordered list of session ULIDs from the ``session_participants`` table.
    traits:
        Core and Role trait slots grouped as ``{active: [...], past: [...]}``.
    magic_effects:
        Magic effects grouped as ``{active: [...], past: [...]}``.
    """

    bonds: BondGroups = BondGroups()
    locations: LocationTiers = LocationTiers()

    # Full-character mechanical fields — None for simplified characters.
    stress: int | None = None
    free_time: int | None = None
    plot: int | None = None
    gnosis: int | None = None
    skills: dict[str, Any] | None = None
    magic_stats: dict[str, Any] | None = None
    last_session_time_now: int | None = None

    # Computed values — None for simplified characters.
    effective_stress_max: int | None = None
    active_magic_effects_count: int | None = None
    active_trait_count: int | None = None
    active_bond_count: int | None = None

    # Session history — None for simplified characters.
    session_ids: list[str] | None = None

    # Traits and magic effects — None for simplified characters.
    traits: CharacterTraitGroups | None = None
    magic_effects: MagicEffectGroups | None = None
