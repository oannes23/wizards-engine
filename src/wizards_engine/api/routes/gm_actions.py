"""Route handler for POST /api/v1/gm/actions — GM direct action endpoint.

The GM actions endpoint provides a single entry point for all GM-initiated
state mutations that bypass the proposal workflow.  Each call specifies an
``action_type`` and type-specific fields; the endpoint dispatches to the
appropriate service handler and returns the Event created by that action.

Endpoints
---------
POST   /gm/actions    — GM only.  Dispatch a direct GM action.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import require_gm
from wizards_engine.api.responses import error_response, raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.event import EventResponse
from wizards_engine.schemas.gm_actions import GmActionRequest
from wizards_engine.services.gm_actions import dispatch_gm_action

router = APIRouter()


@router.post(
    "/gm/actions",
    response_model=EventResponse,
    status_code=200,
    summary="Perform a GM direct action",
    description=(
        "GM only.  Dispatches a direct state-mutation action by ``action_type``.  "
        "Returns the Event created as a result of the action.  "
        "Supported action types: ``modify_character``, ``modify_group``, "
        "``modify_location``, ``modify_clock``, ``create_bond``, "
        "``modify_bond``, ``retire_bond``, ``create_trait``, ``modify_trait``, "
        "``retire_trait``, ``create_effect``, ``modify_effect``, "
        "``retire_effect``, ``award_xp``."
    ),
)
def perform_gm_action(
    body: Annotated[GmActionRequest, ...],
    gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> EventResponse:
    """Perform a GM direct action and return the resulting event.

    Dispatches to the appropriate service handler based on
    ``body.action_type``.  The handler mutates state, creates an event,
    and commits.  Supported action types: ``modify_character``,
    ``modify_group``, ``modify_location``, ``modify_clock``,
    ``create_bond``, ``modify_bond``, ``retire_bond``, ``create_trait``,
    ``modify_trait``, ``retire_trait``, ``create_effect``,
    ``modify_effect``, ``retire_effect``, ``award_xp``.

    Args:
        body: Validated request body.  The ``action_type`` field
            determines which handler is invoked.
        gm: The authenticated GM user (injected; enforces GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``EventResponse`` for the event created by the action.

    Raises:
        HTTPException(404): If the target object does not exist.
        HTTPException(422): If the action payload is logically invalid
            (e.g. visibility out-of-range, circular location hierarchy,
            or simplified character targeted).
    """
    try:
        event = dispatch_gm_action(db, gm, body.action_type, body)
    except ValueError as exc:
        msg = str(exc)
        # Determine the right HTTP status from the error message content.
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "not_found",
                        "message": msg,
                    }
                },
            )
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": msg,
                }
            },
        )


    return EventResponse.model_validate(event)
