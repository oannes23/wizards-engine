"""Route handlers for GM dashboard endpoints.

Endpoints
---------
GET    /gm/dashboard       — GM only.  Aggregated game-state overview.
GET    /gm/queue-summary   — GM only.  PC cards + group cards for queue view.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wizards_engine.api.deps import require_gm
from wizards_engine.db import get_db
from wizards_engine.services.proposal.constants import (
    FREE_TIME_MAX,
    GNOSIS_MAX,
    PLOT_MAX,
    STRESS_MAX,
)
from wizards_engine.models.user import User
from wizards_engine.schemas.gm_dashboard import (
    ActiveClockSummary,
    GmDashboardResponse,
    GmQueueSummaryResponse,
    GroupQueueCard,
    LowChargeItem,
    NearCompletionClock,
    PCSummary,
    PCQueueCard,
    PendingProposalSummary,
    RecentEventSummary,
    StressProximityEntry,
)
from wizards_engine.services.gm_dashboard import (
    get_near_completion_clocks,
    get_pc_summaries,
    get_pending_proposals,
    get_queue_summary,
    get_stress_proximity,
)
from wizards_engine.services.shared import count_trauma_bonds

router = APIRouter()


@router.get(
    "/gm/dashboard",
    response_model=GmDashboardResponse,
    status_code=200,
    summary="GM Dashboard — aggregated game state overview",
    description=(
        "GM only.  Returns four aggregated lists: all pending proposals "
        "(system-origin first, then oldest first), key meter summaries for "
        "all active full characters (sorted by name), clocks that are "
        "one segment away from completion, and PCs within 2 stress of "
        "their effective stress maximum."
    ),
)
def gm_dashboard(
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> GmDashboardResponse:
    """Return aggregated game-state data for the GM dashboard.

    Queries three independent data sources and assembles them into a single
    response.  All queries are read-only.

    Args:
        _gm: The authenticated GM user (injected; enforces GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.gm_dashboard.GmDashboardResponse`
        containing pending proposals, PC meter summaries, and near-completion
        clocks.
    """
    proposals = get_pending_proposals(db)
    characters = get_pc_summaries(db)
    clocks = get_near_completion_clocks(db)
    stress_proximity_data = get_stress_proximity(db)

    return GmDashboardResponse(
        pending_proposals=[
            PendingProposalSummary.model_validate(p) for p in proposals
        ],
        pc_summaries=[
            PCSummary(
                id=c.id,
                name=c.name,
                stress=c.stress or 0,
                stress_max=STRESS_MAX - count_trauma_bonds(db, c.id),
                free_time=c.free_time or 0,
                free_time_max=FREE_TIME_MAX,
                plot=c.plot or 0,
                plot_max=PLOT_MAX,
                gnosis=c.gnosis or 0,
                gnosis_max=GNOSIS_MAX,
            )
            for c in characters
        ],
        near_completion_clocks=[
            NearCompletionClock.model_validate(c) for c in clocks
        ],
        stress_proximity=[
            StressProximityEntry(**entry) for entry in stress_proximity_data
        ],
    )


@router.get(
    "/gm/queue-summary",
    response_model=GmQueueSummaryResponse,
    status_code=200,
    summary="GM Queue Summary — PC cards and group cards for the queue view",
    description=(
        "GM only.  Returns PC cards with current meter values and maximums, "
        "low-charge trait/bond indicators, and recent events per PC; plus "
        "group cards with active clocks and recent events, sorted by "
        "most-recent-event descending."
    ),
)
def gm_queue_summary(
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> GmQueueSummaryResponse:
    """Return PC cards and group cards for the GM queue view.

    Assembles per-character meter data (with computed maximums), low-charge
    slot indicators, and recent event summaries; and per-group clock and
    event data.  All queries are read-only.

    Args:
        _gm: The authenticated GM user (injected; enforces GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        :class:`~wizards_engine.schemas.gm_dashboard.GmQueueSummaryResponse`
        containing ``pc_cards`` and ``group_cards``.
    """
    summary = get_queue_summary(db)

    pc_cards = [
        PCQueueCard(
            id=card["id"],
            name=card["name"],
            stress=card["stress"],
            stress_max=card["stress_max"],
            free_time=card["free_time"],
            free_time_max=card["free_time_max"],
            plot=card["plot"],
            plot_max=card["plot_max"],
            gnosis=card["gnosis"],
            gnosis_max=card["gnosis_max"],
            low_charge_traits=[LowChargeItem(**item) for item in card["low_charge_traits"]],
            low_charge_bonds=[LowChargeItem(**item) for item in card["low_charge_bonds"]],
            recent_events=[RecentEventSummary(**evt) for evt in card["recent_events"]],
        )
        for card in summary["pc_cards"]
    ]

    group_cards = [
        GroupQueueCard(
            id=card["id"],
            name=card["name"],
            tier=card["tier"],
            active_clocks=[ActiveClockSummary(**clk) for clk in card["active_clocks"]],
            recent_events=[RecentEventSummary(**evt) for evt in card["recent_events"]],
            most_recent_event_at=card["most_recent_event_at"],
        )
        for card in summary["group_cards"]
    ]

    return GmQueueSummaryResponse(pc_cards=pc_cards, group_cards=group_cards)
