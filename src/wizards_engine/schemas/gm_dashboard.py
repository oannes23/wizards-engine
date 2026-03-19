"""Response schemas for GET /api/v1/gm/dashboard — GM dashboard aggregation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PendingProposalSummary(BaseModel):
    """Lightweight summary of a pending Proposal for the GM dashboard.

    Attributes
    ----------
    id:
        ULID of the proposal.
    character_id:
        ULID of the submitting character, or ``None`` for system-generated
        proposals (e.g. ``resolve_clock``).
    action_type:
        The proposal's action type string (e.g. ``"use_skill"``).
    origin:
        ``"player"`` or ``"system"``.
    narrative:
        Player-supplied narrative text, or ``None``.
    status:
        Always ``"pending"`` in this context (filter applied server-side).
    created_at:
        UTC timestamp of proposal creation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    character_id: str | None
    action_type: str
    origin: str
    narrative: str | None
    status: str
    created_at: datetime


class PCSummary(BaseModel):
    """Key meters for a single full (PC-level) character.

    Attributes
    ----------
    id:
        ULID of the character.
    name:
        Display name.
    stress:
        Current stress value (0 if the DB column is null).
    free_time:
        Current free-time tokens (0 if null).
    plot:
        Current plot tokens (0 if null).
    gnosis:
        Current gnosis level (0 if null).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    stress: int
    free_time: int
    plot: int
    gnosis: int


class NearCompletionClock(BaseModel):
    """A clock that is one segment away from completion.

    Attributes
    ----------
    id:
        ULID of the clock.
    name:
        Display name.
    progress:
        Current progress value.
    segments:
        Total number of segments (completion threshold).
    associated_type:
        Polymorphic type tag of the associated object, or ``None``.
    associated_id:
        ULID of the associated object, or ``None``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    progress: int
    segments: int
    associated_type: str | None
    associated_id: str | None


class GmDashboardResponse(BaseModel):
    """Aggregated game-state overview for the GM dashboard.

    Attributes
    ----------
    pending_proposals:
        All pending proposals, system-origin first, then oldest first.
    pc_summaries:
        Key meters for all active full (PC-level) characters, sorted by name.
    near_completion_clocks:
        Clocks currently one segment away from completion (not yet completed
        and not deleted).
    """

    pending_proposals: list[PendingProposalSummary]
    pc_summaries: list[PCSummary]
    near_completion_clocks: list[NearCompletionClock]
