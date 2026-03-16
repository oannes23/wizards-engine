"""Route handlers for /api/v1/sessions — Session CRUD and participant endpoints.

Provides CRUD for the Session resource with draft-only lifecycle constraints.
Sessions always start as ``draft``.  Only draft sessions may be deleted (hard
delete).  Only draft or active sessions may be PATCH-updated.

Endpoints
---------
POST   /sessions                                   — GM only.  Create a draft session.
GET    /sessions                                   — Authenticated.  List all sessions with pagination.
GET    /sessions/{id}                              — Authenticated.  Session detail with participants.
PATCH  /sessions/{id}                              — GM only.  Update allowed fields (draft/active only).
DELETE /sessions/{id}                              — GM only.  Hard delete (draft only).
POST   /sessions/{id}/participants                 — Player or GM.  Register a participant.
DELETE /sessions/{id}/participants/{character_id}  — Player self-remove or GM.  Remove a participant.
PATCH  /sessions/{id}/participants/{character_id}  — Player or GM.  Update contribution flag (draft only).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.db import get_db
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.user import User
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.session import (
    AddParticipantRequest,
    CreateSessionRequest,
    ParticipantResponse,
    SessionListResponse,
    SessionResponse,
    UpdateParticipantRequest,
    UpdateSessionRequest,
)
from wizards_engine.services import session as session_svc

router = APIRouter()


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=201,
    summary="Create a session",
    description=(
        "GM only.  Creates a new session with ``status = 'draft'``.  "
        "All fields are optional at creation time.  "
        "``time_now`` must be >= the highest ``time_now`` among ended sessions "
        "(if any ended sessions exist with ``time_now`` set)."
    ),
)
def create_session(
    body: CreateSessionRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Create a new draft session.

    Args:
        body: Validated request body with optional session fields.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``SessionResponse`` for the newly created session (201).

    Raises:
        HTTPException(400): If ``time_now`` would go backwards relative to
            ended sessions.
    """
    if body.time_now is not None:
        error = session_svc.validate_time_now(db, body.time_now)
        if error:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "invalid_time_now",
                        "message": error,
                    }
                },
            )

    session = session_svc.create_session(
        db,
        time_now=body.time_now,
        date=body.date,
        summary=body.summary,
        notes=body.notes,
    )
    return SessionResponse.model_validate(session)


@router.get(
    "/sessions",
    response_model=PaginatedResponse[SessionListResponse],
    status_code=200,
    summary="List sessions",
    description=(
        "Returns a paginated list of all sessions (no status filter — all states "
        "are included).  ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_sessions(
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[SessionListResponse]:
    """Return a paginated list of all sessions.

    Args:
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``SessionListResponse`` objects.
    """
    q = session_svc.list_sessions_query(db)
    page = paginate(db, q, model=SessionModel, after=after, limit=limit)

    return PaginatedResponse[SessionListResponse](
        items=[SessionListResponse.model_validate(s) for s in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    status_code=200,
    summary="Get session detail",
    description=(
        "Returns the full session record including the participants list.  "
        "Returns 404 if no session exists with that ID."
    ),
)
def get_session(
    session_id: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Return a single session by ID with its participant list.

    Args:
        session_id: ULID of the session to retrieve.
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``SessionResponse`` for the requested session, including participants.

    Raises:
        HTTPException(404): If no session exists with ``session_id``.
    """
    session = session_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Session '{session_id}' not found.",
                }
            },
        )
    return SessionResponse.model_validate(session)


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    status_code=200,
    summary="Update a session",
    description=(
        "GM only.  Partial update for ``time_now``, ``date``, ``summary``, ``notes``.  "
        "Only allowed when session ``status`` is ``draft`` or ``active``.  "
        "Returns 400 for ended sessions.  "
        "Omitted fields are unchanged; sending ``null`` clears a nullable field."
    ),
)
def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Apply a partial update to a session.

    Args:
        session_id: ULID of the session to update.
        body: Validated partial update.  Only explicitly provided fields are
            applied (``model_fields_set`` semantics).
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``SessionResponse`` with updated fields.

    Raises:
        HTTPException(404): If the session does not exist.
        HTTPException(400): If the session is ``ended`` (read-only) or
            ``time_now`` would go backwards.
    """
    session = session_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Session '{session_id}' not found.",
                }
            },
        )

    if session.status == "ended":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "session_ended",
                    "message": "Ended sessions are read-only and cannot be updated.",
                }
            },
        )

    updates = body.model_dump(exclude_unset=True)

    # Validate time_now if it was explicitly provided in this PATCH.
    if "time_now" in updates and updates["time_now"] is not None:
        error = session_svc.validate_time_now(db, updates["time_now"])
        if error:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "invalid_time_now",
                        "message": error,
                    }
                },
            )

    session = session_svc.update_session(db, session, updates)
    return SessionResponse.model_validate(session)


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    summary="Delete a session",
    description=(
        "GM only.  Hard-deletes a ``draft`` session.  "
        "Returns 400 if the session is ``active`` or ``ended`` — "
        "only draft sessions can be deleted.  "
        "Returns 204 with no body on success."
    ),
)
def delete_session(
    session_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Hard-delete a draft session.

    Args:
        session_id: ULID of the session to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no session exists with ``session_id``.
        HTTPException(400): If the session is not in ``draft`` status.
    """
    session = session_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Session '{session_id}' not found.",
                }
            },
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "session_not_draft",
                    "message": (
                        f"Only draft sessions can be deleted. "
                        f"This session has status '{session.status}'."
                    ),
                }
            },
        )

    session_svc.delete_session(db, session)


# ---------------------------------------------------------------------------
# Session participant endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/participants",
    response_model=ParticipantResponse,
    status_code=201,
    summary="Register a session participant",
    description=(
        "Player or GM.  Registers a character as a session participant.  "
        "``additional_contribution`` defaults to ``false``.  "
        "Players may only register their own character; GM can register any.  "
        "The character must exist and have ``detail_level = 'full'``.  "
        "Returns 409 if the character is already registered for this session.  "
        "Session must exist (404 otherwise)."
    ),
)
def add_participant(
    session_id: str,
    body: AddParticipantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ParticipantResponse:
    """Register a character as a participant in a session.

    Args:
        session_id: ULID of the session.
        body: Validated request body with ``character_id`` and optional
            ``additional_contribution``.
        current_user: Authenticated user (player or GM).
        db: Injected SQLAlchemy session.

    Returns:
        ``ParticipantResponse`` for the newly created participant (201).

    Raises:
        HTTPException(404): If the session or character does not exist.
        HTTPException(400): If the character is not a full character.
        HTTPException(403): If a player attempts to register a character they
            do not own.
        HTTPException(409): If the character is already registered for this
            session.
    """
    session = session_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Session '{session_id}' not found.",
                }
            },
        )

    # Player ownership check — GM bypasses.
    if current_user.role != "gm":
        if current_user.character_id != body.character_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "character_not_owned",
                        "message": "You can only register your own character.",
                    }
                },
            )

    # Validate character exists and is a full character.
    character = session_svc.get_character(db, body.character_id)
    if character is None or character.is_deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Character '{body.character_id}' not found.",
                }
            },
        )
    if character.detail_level != "full":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "character_not_full",
                    "message": (
                        "Only full characters (PCs) can be registered as participants."
                    ),
                }
            },
        )

    # Duplicate check.
    existing = session_svc.get_participant(db, session_id, body.character_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "already_registered",
                    "message": (
                        f"Character '{body.character_id}' is already registered "
                        f"for this session."
                    ),
                }
            },
        )

    participant = session_svc.add_participant(
        db,
        session,
        character_id=body.character_id,
        additional_contribution=body.additional_contribution,
    )
    return ParticipantResponse.model_validate(participant)


@router.delete(
    "/sessions/{session_id}/participants/{character_id}",
    status_code=204,
    summary="Remove a session participant",
    description=(
        "Player self-remove or GM.  Removes a registered participant from the session.  "
        "No resource clawback for active sessions — removal only affects the participant list.  "
        "Returns 204 with no body on success."
    ),
)
def remove_participant(
    session_id: str,
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a participant from a session.

    Args:
        session_id: ULID of the session.
        character_id: ULID of the character to remove.
        current_user: Authenticated user (player or GM).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If the session or participant does not exist.
        HTTPException(403): If a player attempts to remove a participant that
            is not their own character.
    """
    session = session_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Session '{session_id}' not found.",
                }
            },
        )

    participant = session_svc.get_participant(db, session_id, character_id)
    if participant is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": (
                        f"Participant '{character_id}' not found in session "
                        f"'{session_id}'."
                    ),
                }
            },
        )

    # Player authorization — players can only remove themselves.
    if current_user.role != "gm":
        if current_user.character_id != character_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "character_not_owned",
                        "message": "You can only remove your own character from a session.",
                    }
                },
            )

    session_svc.remove_participant(db, participant)


@router.patch(
    "/sessions/{session_id}/participants/{character_id}",
    response_model=ParticipantResponse,
    status_code=200,
    summary="Update a session participant",
    description=(
        "Player or GM.  Updates the ``additional_contribution`` flag.  "
        "Only allowed when the session is in ``draft`` status.  "
        "Returns 400 for active or ended sessions.  "
        "Players can only update their own participant record; GM can update any."
    ),
)
def update_participant(
    session_id: str,
    character_id: str,
    body: UpdateParticipantRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ParticipantResponse:
    """Update the contribution flag for a session participant.

    Args:
        session_id: ULID of the session.
        character_id: ULID of the character whose participant record to update.
        body: Validated request body with the new ``additional_contribution`` value.
        current_user: Authenticated user (player or GM).
        db: Injected SQLAlchemy session.

    Returns:
        ``ParticipantResponse`` with the updated flag (200).

    Raises:
        HTTPException(404): If the session or participant does not exist.
        HTTPException(400): If the session is not in ``draft`` status.
        HTTPException(403): If a player attempts to update another player's
            participant record.
    """
    session = session_svc.get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Session '{session_id}' not found.",
                }
            },
        )

    if session.status != "draft":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "session_not_draft",
                    "message": (
                        "Participant contribution flag can only be updated for "
                        "draft sessions."
                    ),
                }
            },
        )

    participant = session_svc.get_participant(db, session_id, character_id)
    if participant is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": (
                        f"Participant '{character_id}' not found in session "
                        f"'{session_id}'."
                    ),
                }
            },
        )

    # Player authorization — players can only update their own record.
    if current_user.role != "gm":
        if current_user.character_id != character_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "character_not_owned",
                        "message": "You can only update your own participant record.",
                    }
                },
            )

    participant = session_svc.update_participant_contribution(
        db, participant, body.additional_contribution
    )
    return ParticipantResponse.model_validate(participant)
