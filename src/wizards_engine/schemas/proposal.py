"""Pydantic schemas for Proposal API endpoints.

Covers request bodies and the response shape for
``/api/v1/proposals``.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# ---------------------------------------------------------------------------
# Valid action types
# ---------------------------------------------------------------------------

VALID_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "use_skill",
        "use_magic",
        "charge_magic",
        "regain_gnosis",
        "work_on_project",
        "rest",
        "new_trait",
        "new_bond",
        "resolve_clock",
        "resolve_trauma",
    }
)

# These action types are reserved for system-generated proposals.
# Players cannot submit proposals with these types.
SYSTEM_ONLY_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "resolve_clock",
        "resolve_trauma",
    }
)

#: Session action types — narrative is optional for these.
SESSION_ACTION_TYPES: frozenset[str] = frozenset({"use_skill", "use_magic", "charge_magic"})

#: Downtime proposal types — narrative is required for these.
DOWNTIME_PROPOSAL_TYPES: frozenset[str] = frozenset(
    {"regain_gnosis", "work_on_project", "rest", "new_trait", "new_bond"}
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateProposalRequest(BaseModel):
    """Request body for POST /api/v1/proposals.

    Attributes
    ----------
    character_id:
        ULID of the character submitting the proposal.  Must belong to the
        authenticated user (``user.character_id == character_id``).
    action_type:
        One of the 9 player-submittable action types.  ``resolve_clock``
        and ``resolve_trauma`` are system-only and will be rejected.
    narrative:
        Player-written description of the intended action.  Optional for
        session action types (``use_skill``, ``use_magic``, ``charge_magic``);
        required for downtime action types.
    selections:
        Type-specific inputs (modifier trait/bond IDs, plot_spend, etc.).
        Full validation of the contents is deferred to later stories.
    """

    character_id: str
    action_type: str
    narrative: str | None = None
    selections: dict = {}

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        """Ensure action_type is valid and player-submittable."""
        if v not in VALID_ACTION_TYPES:
            raise ValueError(
                f"action_type must be one of: {sorted(VALID_ACTION_TYPES)}"
            )
        if v in SYSTEM_ONLY_ACTION_TYPES:
            raise ValueError(
                f"action_type '{v}' is system-generated and cannot be submitted by players"
            )
        return v

    @field_validator("selections")
    @classmethod
    def validate_selections_is_dict(cls, v: dict) -> dict:
        """Ensure selections is a dict (type-specific validation deferred)."""
        if not isinstance(v, dict):
            raise ValueError("selections must be a JSON object")
        return v

    @model_validator(mode="after")
    def validate_narrative_for_downtime(self) -> "CreateProposalRequest":
        """Downtime actions require a non-empty narrative."""
        if self.action_type in DOWNTIME_PROPOSAL_TYPES:
            if not self.narrative or not self.narrative.strip():
                raise ValueError("Narrative is required for downtime actions")
        return self


class UpdateProposalRequest(BaseModel):
    """Request body for PATCH /api/v1/proposals/{id}.

    Attributes
    ----------
    narrative:
        Updated narrative text.  Omit to leave unchanged.
    selections:
        Updated selections dict.  Omit to leave unchanged.
    """

    narrative: str | None = None
    selections: dict | None = None


class RiderEventPayload(BaseModel):
    """Nested payload for an optional rider event attached to a proposal approval.

    Attributes
    ----------
    type:
        Convention-based event type string (e.g. ``"clock.advanced"``).
    targets:
        List of ``{target_type, target_id, is_primary}`` dicts.
    changes:
        Mapping of change keys to ``{op, before, after}`` dicts.
    narrative:
        Human-readable description of the rider event.
    visibility:
        One of the 7 canonical visibility levels.
    metadata:
        Optional freeform JSON.
    """

    type: str
    targets: list[dict] = []
    changes: dict = {}
    narrative: str | None = None
    visibility: str = "bonded"
    metadata: dict | None = None


class ApproveProposalRequest(BaseModel):
    """Request body for POST /api/v1/proposals/{id}/approve.

    Attributes
    ----------
    narrative:
        Optional GM narrative override for the approval event.  If omitted,
        the player's original narrative is used.
    gm_overrides:
        Optional dict of replacement values for ``calculated_effect`` fields.
        Special keys: ``bond_strained`` (bool) — strain the modifier bond;
        ``force`` (bool) — force approval despite insufficient resources.
    rider_event:
        Optional rider event created atomically in the same transaction.
    """

    narrative: str | None = None
    gm_overrides: dict | None = None
    rider_event: RiderEventPayload | None = None


class RejectProposalRequest(BaseModel):
    """Request body for POST /api/v1/proposals/{id}/reject.

    Attributes
    ----------
    rejection_note:
        Optional GM-written reason for rejection.  Stored in
        ``proposal.gm_notes``.
    """

    rejection_note: str | None = None


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class ProposalResponse(BaseModel):
    """Response body for a single Proposal resource.

    Returned by POST, GET, and PATCH proposal endpoints.

    Attributes
    ----------
    id:
        ULID primary key.
    character_id:
        ULID of the submitting character, or ``None`` for system proposals.
    action_type:
        The action type string.
    origin:
        ``"player"`` or ``"system"``.
    narrative:
        Player-written (or system-generated) description.
    selections:
        Type-specific input dict.
    calculated_effect:
        System-computed result dict, or ``None`` if not yet calculated.
    status:
        ``"pending"``, ``"approved"``, or ``"rejected"``.
    gm_notes:
        GM annotations on the proposal, or ``None``.
    gm_overrides:
        GM overrides to the calculated_effect, or ``None``.
    event_id:
        ULID of the event generated on approval, or ``None``.
    rider_event_id:
        ULID of a rider event generated on approval, or ``None``.
    clock_id:
        ULID of a linked clock (``resolve_clock`` proposals only), or ``None``.
    created_at:
        ISO 8601 UTC creation timestamp.
    updated_at:
        ISO 8601 UTC last-updated timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    character_id: str | None
    action_type: str
    origin: str
    narrative: str | None
    selections: dict
    calculated_effect: dict | None
    status: str
    revision_count: int
    gm_notes: str | None
    gm_overrides: dict | None
    event_id: str | None
    rider_event_id: str | None
    clock_id: str | None
    created_at: datetime
    updated_at: datetime
    character_name: str | None = None
    clock_name: str | None = None
    selection_entities: dict[str, str] = {}


class CalculateEffectResponse(BaseModel):
    """Response body for POST /api/v1/proposals/calculate.

    Wraps the computed ``calculated_effect`` dict without creating a
    proposal record.

    Attributes
    ----------
    calculated_effect:
        The server-computed effect for the given action type and
        selections.  Shape is action-type-specific.
    """

    calculated_effect: dict
