"""Response schemas for GM dashboard endpoints.

Covers:
- GET /api/v1/gm/dashboard — aggregated game-state overview
- GET /api/v1/gm/queue-summary — PC cards with meters, low-charge indicators,
  recent events, and group cards with active clocks
"""

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


class StressProximityEntry(BaseModel):
    """A PC that is within 2 stress of their effective stress maximum.

    Attributes
    ----------
    character_id:
        ULID of the character.
    character_name:
        Display name.
    current_stress:
        The character's current stress value.
    effective_max:
        Computed effective stress maximum (9 minus trauma bond count).
    margin:
        How many stress points remain before the character hits their
        maximum (``effective_max - current_stress``).
    """

    character_id: str
    character_name: str
    current_stress: int
    effective_max: int
    margin: int


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
    stress_proximity:
        PCs within 2 stress of their effective stress maximum (9 minus
        trauma bond count).
    """

    pending_proposals: list[PendingProposalSummary]
    pc_summaries: list[PCSummary]
    near_completion_clocks: list[NearCompletionClock]
    stress_proximity: list[StressProximityEntry]


# ---------------------------------------------------------------------------
# Queue Summary schemas (GET /api/v1/gm/queue-summary)
# ---------------------------------------------------------------------------


class LowChargeItem(BaseModel):
    """A trait or bond with a charge value at or below the low-charge threshold.

    Attributes
    ----------
    id:
        ULID of the slot.
    name:
        Display name of the trait or bond.
    slot_type:
        One of ``"core_trait"``, ``"role_trait"``, or ``"pc_bond"``.
    charge:
        Current charge value (0–5 for traits; 0–5 for bond charges).
    """

    id: str
    name: str
    slot_type: str
    charge: int


class RecentEventSummary(BaseModel):
    """A brief summary of an event targeting a PC or group.

    Attributes
    ----------
    id:
        ULID of the event.
    type:
        Event type string (e.g. ``"use_skill"``, ``"gm_direct_action"``).
    created_at:
        UTC timestamp when the event was created.
    """

    id: str
    type: str
    created_at: datetime


class ActiveClockSummary(BaseModel):
    """A non-completed clock associated with a group.

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
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    progress: int
    segments: int


class PCQueueCard(BaseModel):
    """Information-dense summary of a PC for the GM queue view.

    Includes current meter values with computed maximums, low-charge trait
    and bond indicators, and the most recent events targeting this character.

    Attributes
    ----------
    id:
        ULID of the character.
    name:
        Display name.
    stress:
        Current stress value.
    stress_max:
        Effective stress maximum (9 minus active trauma bond count).
    free_time:
        Current free-time tokens.
    free_time_max:
        Maximum free-time tokens (always 20).
    plot:
        Current plot tokens.
    plot_max:
        Maximum plot tokens (always 5).
    gnosis:
        Current gnosis level.
    gnosis_max:
        Maximum gnosis level (always 23).
    low_charge_traits:
        Active core/role traits with charge <= 2.
    low_charge_bonds:
        Active non-trauma pc_bonds with charges <= 2.
    recent_events:
        The last 3 events targeting this character, newest first.
    """

    id: str
    name: str
    stress: int
    stress_max: int
    free_time: int
    free_time_max: int
    plot: int
    plot_max: int
    gnosis: int
    gnosis_max: int
    low_charge_traits: list[LowChargeItem]
    low_charge_bonds: list[LowChargeItem]
    recent_events: list[RecentEventSummary]


class GroupQueueCard(BaseModel):
    """Summary of a group for the GM queue view.

    Includes active clocks and the most recent events targeting this group.

    Attributes
    ----------
    id:
        ULID of the group.
    name:
        Display name.
    tier:
        Tier level (integer).
    active_clocks:
        All non-completed, non-deleted clocks associated with this group.
    recent_events:
        The last 3 events targeting this group, newest first.
    most_recent_event_at:
        UTC timestamp of the most recent event targeting this group, or
        ``None`` if no events exist.  Used for server-side sorting; included
        in the response for client convenience.
    """

    id: str
    name: str
    tier: int
    active_clocks: list[ActiveClockSummary]
    recent_events: list[RecentEventSummary]
    most_recent_event_at: datetime | None


class GmQueueSummaryResponse(BaseModel):
    """Response for GET /api/v1/gm/queue-summary.

    Attributes
    ----------
    pc_cards:
        One card per active full (PC-level) character, sorted by name.
    group_cards:
        One card per active group, sorted by most-recent-event descending
        (groups with no events appear last).
    """

    pc_cards: list[PCQueueCard]
    group_cards: list[GroupQueueCard]
