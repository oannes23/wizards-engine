"""Route handler for GET /api/v1/gm/dashboard — GM dashboard aggregation.

Returns a single response aggregating pending proposals, PC meter summaries,
and clocks that are one segment away from completion.  GM-only.

Endpoints
---------
GET    /gm/dashboard    — GM only.  Aggregated game-state overview.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wizards_engine.api.deps import require_gm
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.gm_dashboard import (
    GmDashboardResponse,
    NearCompletionClock,
    PCSummary,
    PendingProposalSummary,
)
from wizards_engine.services.gm_dashboard import (
    get_near_completion_clocks,
    get_pc_summaries,
    get_pending_proposals,
)

router = APIRouter()


@router.get(
    "/gm/dashboard",
    response_model=GmDashboardResponse,
    status_code=200,
    summary="GM Dashboard — aggregated game state overview",
    description=(
        "GM only.  Returns three aggregated lists: all pending proposals "
        "(system-origin first, then oldest first), key meter summaries for "
        "all active full characters (sorted by name), and clocks that are "
        "one segment away from completion."
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

    return GmDashboardResponse(
        pending_proposals=[
            PendingProposalSummary.model_validate(p) for p in proposals
        ],
        pc_summaries=[
            PCSummary(
                id=c.id,
                name=c.name,
                stress=c.stress or 0,
                free_time=c.free_time or 0,
                plot=c.plot or 0,
                gnosis=c.gnosis or 0,
            )
            for c in characters
        ],
        near_completion_clocks=[
            NearCompletionClock.model_validate(c) for c in clocks
        ],
    )
