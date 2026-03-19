"""Route handler for POST /api/v1/gm/actions/batch — batch GM actions endpoint.

Executes multiple GM actions atomically.  If any action fails, the entire
batch is rolled back and no state changes are persisted.

Endpoints
---------
POST   /gm/actions/batch    — GM only.  Execute multiple GM actions atomically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from wizards_engine.api.deps import require_gm
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.event import EventResponse
from wizards_engine.schemas.gm_actions import GmActionRequest
from wizards_engine.services.gm_actions import dispatch_gm_action

router = APIRouter()


class BatchGmActionsRequest(BaseModel):
    """Request body for POST /gm/actions/batch.

    Attributes
    ----------
    actions:
        List of GM actions to execute atomically.  Must contain between 1
        and 50 items (inclusive).
    """

    actions: list[GmActionRequest]

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: list) -> list:
        """Validate that the actions list is non-empty and within size limits.

        Args:
            v: The list of actions to validate.

        Returns:
            The validated list.

        Raises:
            ValueError: If the list is empty (``batch_empty``) or exceeds
                50 items (``batch_too_large``).
        """
        if len(v) == 0:
            raise ValueError("batch_empty")
        if len(v) > 50:
            raise ValueError("batch_too_large")
        return v


class BatchGmActionsResponse(BaseModel):
    """Response body for POST /gm/actions/batch.

    Attributes
    ----------
    events:
        List of events created by the batch, in the same order as the
        input actions.
    """

    events: list[EventResponse]


@router.post(
    "/gm/actions/batch",
    response_model=BatchGmActionsResponse,
    status_code=200,
    summary="Batch GM actions — execute multiple actions atomically",
    description=(
        "GM only.  Executes a list of GM direct-action requests atomically — "
        "if any action fails, the entire batch is rolled back.  Returns the "
        "list of Events created, in the same order as the input actions.  "
        "The batch must contain 1–50 actions."
    ),
)
def batch_gm_actions(
    body: BatchGmActionsRequest,
    gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> BatchGmActionsResponse:
    """Execute a batch of GM direct actions atomically.

    Each service handler calls ``db.commit()`` internally.  To preserve
    full-batch atomicity, the session's ``commit`` method is temporarily
    replaced with ``db.flush`` for the duration of the batch.  This causes
    each handler to flush pending state (making it visible within the
    session) without issuing an actual database COMMIT.

    If any action raises, an HTTPException is raised — causing ``get_db``
    to roll back the entire transaction, undoing all work from the batch.

    Once all actions succeed, ``db.commit`` is restored and the outer
    ``get_db`` dependency commits the transaction in the normal path.

    Args:
        body: Validated request body containing 1–50 GM actions.
        gm: The authenticated GM user (injected; enforces GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``BatchGmActionsResponse`` containing the list of events created
        by the batch, in input order.

    Raises:
        HTTPException(422): If any action fails validation or a target
            does not exist.  The ``detail.error`` object includes
            ``failed_index`` (0-based) and ``detail`` (the error message).
    """
    events = []

    # Temporarily replace db.commit with db.flush so that the individual
    # handler commits do not issue real COMMIT statements.  This keeps all
    # writes inside the current transaction so the outer get_db dependency
    # can commit or roll back the entire batch atomically.
    _real_commit = db.commit
    db.commit = db.flush  # type: ignore[method-assign]

    try:
        for idx, action in enumerate(body.actions):
            try:
                event = dispatch_gm_action(db, gm, action.action_type, action)
                # After each handler's flush, refresh the event to ensure
                # all fields (including auto-generated ones) are loaded.
                db.refresh(event)
                events.append(event)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "batch_failed",
                            "failed_index": idx,
                            "detail": str(exc),
                        }
                    },
                )
    finally:
        # Always restore the real commit method.
        db.commit = _real_commit  # type: ignore[method-assign]

    return BatchGmActionsResponse(
        events=[EventResponse.model_validate(e) for e in events]
    )
