"""Pydantic models for all campaign YAML entity types.

These models validate YAML file content for the import/export system.
They are intentionally independent of SQLAlchemy ORM models — they
represent the human-editable YAML on disk, not the database schema.

Cross-references between entities use human-readable name strings
(not ULIDs), following the campaign format design decision.

Usage example::

    import yaml
    from wizards_engine.campaign.schemas import PCCharacterYaml

    with open("characters/pcs/alexander.yaml") as f:
        data = yaml.safe_load(f)
    char = PCCharacterYaml.model_validate(data)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared / primitive models
# ---------------------------------------------------------------------------


class TargetRef(BaseModel):
    """Polymorphic reference to a game object by type and name.

    Used wherever a bond or association points to another entity.
    The ``type`` field must be one of ``"character"``, ``"group"``,
    or ``"location"``.  The ``name`` field must match the ``name``
    field of the target entity exactly (case-sensitive).

    Attributes
    ----------
    type:
        Entity type — ``"character"``, ``"group"``, or ``"location"``.
    name:
        Human-readable display name of the target entity.
    """

    type: str
    name: str

    @model_validator(mode="after")
    def validate_type(self) -> "TargetRef":
        """Ensure type is a valid game object type."""
        valid_types = {"character", "group", "location"}
        if self.type not in valid_types:
            raise ValueError(
                f"type must be one of {sorted(valid_types)}, got {self.type!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Campaign metadata
# ---------------------------------------------------------------------------


class CampaignMeta(BaseModel):
    """Campaign metadata stored in ``meta.yaml``.

    Attributes
    ----------
    engine_version:
        Semantic version string of the engine that produced this export.
    campaign_name:
        Human-readable campaign title.
    format_version:
        Integer version of the YAML format schema.  Increment on
        breaking changes.
    """

    engine_version: str
    campaign_name: str
    format_version: int = 1


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserYaml(BaseModel):
    """A user account entry.

    Stored in ``users/<slug>.yaml``.

    Attributes
    ----------
    display_name:
        Player's display name (1–50 characters).
    role:
        ``"gm"`` or ``"player"``.
    character:
        Name ref to this user's linked character.  ``None`` for the GM
        (unless the GM is also a player).
    """

    display_name: str
    role: str
    character: str | None = None

    @model_validator(mode="after")
    def validate_role(self) -> "UserYaml":
        """Ensure role is gm or player."""
        if self.role not in {"gm", "player"}:
            raise ValueError(f"role must be 'gm' or 'player', got {self.role!r}")
        return self


# ---------------------------------------------------------------------------
# Trait templates
# ---------------------------------------------------------------------------


class TraitTemplateYaml(BaseModel):
    """A trait template catalog entry.

    Stored in ``trait-templates/<slug>.yaml``.

    Attributes
    ----------
    name:
        Template name.
    type:
        ``"core"`` or ``"role"``.  Fixed — determines which slot type
        can reference this template.
    description:
        Full description text.
    """

    name: str
    type: str
    description: str

    @model_validator(mode="after")
    def validate_type(self) -> "TraitTemplateYaml":
        """Ensure type is core or role."""
        if self.type not in {"core", "role"}:
            raise ValueError(f"type must be 'core' or 'role', got {self.type!r}")
        return self


# ---------------------------------------------------------------------------
# Slot sub-models: traits, bonds, magic effects
# ---------------------------------------------------------------------------


class PCTraitYaml(BaseModel):
    """A single core or role trait on a PC's sheet.

    Inline within ``PCCharacterYaml.core_traits`` or
    ``PCCharacterYaml.role_traits``.

    Attributes
    ----------
    template:
        Name ref to the ``TraitTemplateYaml`` this slot uses.
    charge:
        Current charge count (0–5).  Defaults to 5.
    is_active:
        ``True`` for active traits; ``False`` for retired/past.
    """

    template: str
    charge: int = Field(default=5, ge=0, le=5)
    is_active: bool = True


class PCBondYaml(BaseModel):
    """A single PC bond (pc_bond slot).

    Inline within ``PCCharacterYaml.bonds``.

    Attributes
    ----------
    name:
        Bond name / relationship label.
    target:
        Polymorphic reference to the bond target.
    description:
        Optional narrative description.
    labels:
        Optional ``{source: str, target: str}`` perspective labels.
    charges:
        Bond charges (0–5).  Defaults to 5.
    degradations:
        Degradation count (number of max-charge reductions).  Defaults
        to 0.
    is_trauma:
        ``True`` if this slot holds a Trauma bond.  Defaults to
        ``False``.
    is_active:
        ``True`` for active bonds; ``False`` for retired/past.
    """

    name: str
    target: TargetRef
    description: str | None = None
    labels: dict[str, str] | None = None
    charges: int = Field(default=5, ge=0, le=5)
    degradations: int = Field(default=0, ge=0)
    is_trauma: bool = False
    is_active: bool = True


class NPCBondYaml(BaseModel):
    """A single NPC bond (npc_bond slot).

    Inline within ``NPCCharacterYaml.bonds``.

    Attributes
    ----------
    name:
        Bond name / relationship label.
    target:
        Polymorphic reference to the bond target.
    description:
        Optional narrative description.
    labels:
        Optional ``{source: str, target: str}`` perspective labels.
    bidirectional:
        Whether both sides see this bond.  Defaults to ``False``.
    is_active:
        ``True`` for active bonds; ``False`` for retired/past.
    """

    name: str
    target: TargetRef
    description: str | None = None
    labels: dict[str, str] | None = None
    bidirectional: bool = False
    is_active: bool = True


class MagicEffectYaml(BaseModel):
    """A magic effect on a PC's sheet.

    Inline within ``PCCharacterYaml.magic_effects``.

    Attributes
    ----------
    name:
        Effect name.
    description:
        Full description text.
    effect_type:
        ``"instant"``, ``"charged"``, or ``"permanent"``.
    power_level:
        Power level (1–5).
    charges:
        Current and maximum charges as ``{current: int, max: int}``.
        Only used for ``effect_type = "charged"``; should be ``None``
        for instant and permanent effects.
    is_active:
        ``True`` for active effects; ``False`` for retired/past.
    """

    name: str
    description: str
    effect_type: str
    power_level: int = Field(ge=1, le=5)
    charges: dict[str, int] | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_effect_type(self) -> "MagicEffectYaml":
        """Ensure effect_type is a valid value."""
        if self.effect_type not in {"instant", "charged", "permanent"}:
            raise ValueError(
                f"effect_type must be 'instant', 'charged', or 'permanent', "
                f"got {self.effect_type!r}"
            )
        return self

    @model_validator(mode="after")
    def validate_charges_for_type(self) -> "MagicEffectYaml":
        """Ensure charged effects have a charges dict with current/max keys."""
        if self.effect_type == "charged":
            if self.charges is None:
                raise ValueError(
                    "charges dict is required for charged effects"
                )
            if "current" not in self.charges or "max" not in self.charges:
                raise ValueError(
                    "charges must have 'current' and 'max' keys for charged effects"
                )
        elif self.charges is not None:
            raise ValueError(
                f"charges must be None for {self.effect_type!r} effects"
            )
        return self


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------


class PCCharacterYaml(BaseModel):
    """A full (PC) character entry.

    Stored in ``characters/pcs/<slug>.yaml``.

    Attributes
    ----------
    name:
        Character name.
    detail_level:
        Always ``"full"`` for PC characters.
    description:
        Optional background / concept text.
    notes:
        Optional GM notes.
    secrets:
        Optional GM-only secrets section.  On import, appended to
        ``notes`` with a ``--- Secrets ---`` separator.
    attributes:
        Optional freeform JSON blob.
    meters:
        Dict with keys ``stress``, ``free_time``, ``plot``, ``gnosis``.
    skills:
        Dict with all 8 skill names mapped to their level (0–3).
    magic_stats:
        Dict with all 5 magic stat names, each with ``level`` and
        ``xp`` sub-keys.
    core_traits:
        List of core trait slots (max 2).
    role_traits:
        List of role trait slots (max 3).
    bonds:
        List of PC bond slots (max 8).
    magic_effects:
        List of magic effects (max 9 active charged + permanent).
    """

    name: str
    detail_level: str = "full"
    description: str | None = None
    notes: str | None = None
    secrets: str | None = None
    attributes: dict[str, Any] | None = None
    meters: dict[str, int] = Field(
        default_factory=lambda: {
            "stress": 0,
            "free_time": 0,
            "plot": 0,
            "gnosis": 0,
        }
    )
    skills: dict[str, int] = Field(
        default_factory=lambda: {
            "awareness": 0,
            "composure": 0,
            "influence": 0,
            "finesse": 0,
            "speed": 0,
            "power": 0,
            "knowledge": 0,
            "technology": 0,
        }
    )
    magic_stats: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {
            "being": {"level": 0, "xp": 0},
            "wyrding": {"level": 0, "xp": 0},
            "summoning": {"level": 0, "xp": 0},
            "enchanting": {"level": 0, "xp": 0},
            "dreaming": {"level": 0, "xp": 0},
        }
    )
    core_traits: list[PCTraitYaml] = Field(default_factory=list)
    role_traits: list[PCTraitYaml] = Field(default_factory=list)
    bonds: list[PCBondYaml] = Field(default_factory=list)
    magic_effects: list[MagicEffectYaml] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_detail_level(self) -> "PCCharacterYaml":
        """Ensure detail_level is 'full'."""
        if self.detail_level != "full":
            raise ValueError(
                f"PCCharacterYaml requires detail_level='full', "
                f"got {self.detail_level!r}"
            )
        return self


class NPCCharacterYaml(BaseModel):
    """A simplified (NPC) character entry.

    Stored in ``characters/npcs/<slug>.yaml`` or
    ``characters/entities/<slug>.yaml``.

    Attributes
    ----------
    name:
        Character name.
    detail_level:
        Always ``"simplified"`` for NPC characters.
    description:
        Optional background / concept text.
    notes:
        Optional GM notes.
    secrets:
        Optional GM-only secrets section.  On import, appended to
        ``notes`` with a ``--- Secrets ---`` separator.
    attributes:
        Optional freeform JSON blob for NPC mechanical data.
    bonds:
        List of NPC bond slots (max 7).
    """

    name: str
    detail_level: str = "simplified"
    description: str | None = None
    notes: str | None = None
    secrets: str | None = None
    attributes: dict[str, Any] | None = None
    bonds: list[NPCBondYaml] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_detail_level(self) -> "NPCCharacterYaml":
        """Ensure detail_level is 'simplified'."""
        if self.detail_level != "simplified":
            raise ValueError(
                f"NPCCharacterYaml requires detail_level='simplified', "
                f"got {self.detail_level!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


class GroupTraitYaml(BaseModel):
    """A single group trait (group_trait slot).

    Inline within ``GroupYaml.traits``.

    Attributes
    ----------
    name:
        Trait name.
    description:
        Optional description text.
    is_active:
        ``True`` for active traits; ``False`` for retired/past.
    """

    name: str
    description: str | None = None
    is_active: bool = True


class GroupRelationYaml(BaseModel):
    """A single group relation (group_relation slot).

    Inline within ``GroupYaml.relations``.

    Attributes
    ----------
    name:
        Relation name.
    target:
        Name ref to the target group.
    labels:
        Optional ``{source: str, target: str}`` perspective labels.
    bidirectional:
        Whether both sides see this relation.  Defaults to ``False``.
    is_active:
        ``True`` for active relations; ``False`` for retired/past.
    """

    name: str
    target: str
    description: str | None = None
    labels: dict[str, str] | None = None
    bidirectional: bool = False
    is_active: bool = True


class GroupHoldingYaml(BaseModel):
    """A single group holding (group_holding slot).

    Inline within ``GroupYaml.holdings``.

    Attributes
    ----------
    name:
        Holding name.
    target:
        Name ref to the target location.
    description:
        Optional description text.
    is_active:
        ``True`` for active holdings; ``False`` for retired/past.
    """

    name: str
    target: str
    description: str | None = None
    is_active: bool = True


class GroupYaml(BaseModel):
    """A group (organization/faction) entry.

    Stored in ``groups/<slug>.yaml``.

    Attributes
    ----------
    name:
        Group name.
    description:
        Optional description text.
    tier:
        Power/influence level (any non-negative integer).
    notes:
        Optional GM notes.
    traits:
        Inline group trait slots (max 10).
    relations:
        Inline group relation slots (max 7).
    holdings:
        Inline group holding slots (unlimited).
    """

    name: str
    description: str | None = None
    tier: int = 1
    notes: str | None = None
    traits: list[GroupTraitYaml] = Field(default_factory=list)
    relations: list[GroupRelationYaml] = Field(default_factory=list)
    holdings: list[GroupHoldingYaml] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


class LocationFeatureYaml(BaseModel):
    """A single location feature (feature_trait slot).

    Inline within ``LocationYaml.features``.

    Attributes
    ----------
    name:
        Feature name.
    description:
        Optional description text.
    is_active:
        ``True`` for active features; ``False`` for retired/past.
    """

    name: str
    description: str | None = None
    is_active: bool = True


class LocationBondYaml(BaseModel):
    """A single location bond (location_bond slot).

    Inline within ``LocationYaml.bonds``.

    Attributes
    ----------
    name:
        Bond name.
    target:
        Polymorphic reference to the bond target.
    labels:
        Optional ``{source: str, target: str}`` perspective labels.
    is_active:
        ``True`` for active bonds; ``False`` for retired/past.
    """

    name: str
    target: TargetRef
    description: str | None = None
    labels: dict[str, str] | None = None
    is_active: bool = True


class LocationYaml(BaseModel):
    """A location entry.

    Stored in ``locations/<path>/_location.yaml``.  Directory nesting
    reflects the parent-child hierarchy.

    Attributes
    ----------
    name:
        Location name.
    description:
        Optional description text.
    notes:
        Optional GM notes.
    parent:
        Name ref to the parent location.  ``None`` for top-level
        locations.  On import, resolved from the directory structure
        automatically — this field is used as an override.
    features:
        Inline feature trait slots (max 5).
    bonds:
        Inline location bond slots (unlimited).
    """

    name: str
    description: str | None = None
    notes: str | None = None
    parent: str | None = None
    features: list[LocationFeatureYaml] = Field(default_factory=list)
    bonds: list[LocationBondYaml] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------


class ClockYaml(BaseModel):
    """A progress clock entry.

    Stored in ``clocks/<slug>.yaml``.

    Attributes
    ----------
    name:
        Clock name.
    segments:
        Total segments (any positive integer, default 5).
    progress:
        Filled segments (0 to segments).
    associated_with:
        Optional polymorphic reference to an associated game object.
    notes:
        Optional GM notes.
    """

    name: str
    segments: int = 5
    progress: int = 0
    associated_with: TargetRef | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_segments(self) -> "ClockYaml":
        """Ensure segments is positive."""
        if self.segments < 1:
            raise ValueError(f"segments must be at least 1, got {self.segments}")
        return self

    @model_validator(mode="after")
    def validate_progress(self) -> "ClockYaml":
        """Ensure progress is non-negative."""
        if self.progress < 0:
            raise ValueError(f"progress must be non-negative, got {self.progress}")
        return self


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionParticipantYaml(BaseModel):
    """A single participant in a session.

    Inline within ``SessionYaml.participants``.

    Attributes
    ----------
    character:
        Name ref to the participating character.
    additional_contribution:
        Meta-game reward flag (+1 bonus Plot).  Defaults to ``False``.
    """

    character: str
    additional_contribution: bool = False


class SessionYaml(BaseModel):
    """A play session record.

    Stored in ``sessions/<number>-<slug>.yaml``.

    Attributes
    ----------
    number:
        Sequential session number (used for ordering and references).
    status:
        ``"draft"``, ``"active"``, or ``"ended"``.
    time_now:
        Abstract campaign time counter.  ``None`` if not yet set.
    date:
        Real-world date string (ISO 8601, ``YYYY-MM-DD``).  ``None``
        if not recorded.
    summary:
        Optional session summary text.
    participants:
        List of characters who attended this session.
    """

    number: int
    status: str
    time_now: int | None = None
    date: str | None = None
    summary: str | None = None
    notes: str | None = None
    participants: list[SessionParticipantYaml] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> "SessionYaml":
        """Ensure status is a valid session lifecycle value."""
        if self.status not in {"draft", "active", "ended"}:
            raise ValueError(
                f"status must be 'draft', 'active', or 'ended', "
                f"got {self.status!r}"
            )
        return self


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------


class StoryEntryYaml(BaseModel):
    """A single narrative entry within a story.

    Inline within ``StoryYaml.entries``.

    Attributes
    ----------
    text:
        Narrative content.
    author:
        Display name ref to the user who wrote this entry.
    character:
        Name ref to the optional character linkage.  ``None`` if not
        linked to a specific character.
    session:
        Session number ref to the optional session linkage.  ``None``
        if not linked to a specific session.
    """

    text: str
    author: str
    character: str | None = None
    session: int | None = None


class StoryOwnerYaml(BaseModel):
    """A game object that owns a story.

    Inline within ``StoryYaml.owners``.

    Attributes
    ----------
    type:
        Game object type — ``"character"``, ``"group"``, or
        ``"location"``.
    name:
        Name ref to the owning game object.
    """

    type: str
    name: str

    @model_validator(mode="after")
    def validate_type(self) -> "StoryOwnerYaml":
        """Ensure type is a valid game object type."""
        valid_types = {"character", "group", "location"}
        if self.type not in valid_types:
            raise ValueError(
                f"type must be one of {sorted(valid_types)}, got {self.type!r}"
            )
        return self


class StoryYaml(BaseModel):
    """A narrative story arc entry.

    Stored in ``stories/<slug>.yaml``.

    Attributes
    ----------
    name:
        Story name.
    summary:
        Optional summary text.
    status:
        ``"active"``, ``"completed"``, or ``"abandoned"``.
    tags:
        Optional list of freeform tag strings.
    owners:
        List of game objects that own this story.
    entries:
        Inline narrative entries ordered by creation time.
    children:
        Nested child story arcs.  Each child is a full ``StoryYaml``
        and is imported as a sub-arc linked to this story's ``id``.
    """

    name: str
    summary: str | None = None
    status: str = "active"
    tags: list[str] = Field(default_factory=list)
    owners: list[StoryOwnerYaml] = Field(default_factory=list)
    entries: list[StoryEntryYaml] = Field(default_factory=list)
    children: list["StoryYaml"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> "StoryYaml":
        """Ensure status is a valid story status value."""
        if self.status not in {"active", "completed", "abandoned"}:
            raise ValueError(
                f"status must be 'active', 'completed', or 'abandoned', "
                f"got {self.status!r}"
            )
        return self


# Rebuild model to resolve the forward reference in StoryYaml.children.
StoryYaml.model_rebuild()
