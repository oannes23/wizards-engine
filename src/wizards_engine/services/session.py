"""Service layer for Session CRUD operations.

All database interactions for the Session resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status codes,
response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.

Business rules enforced here:
- Sessions always start as ``draft``.
- PATCH is allowed only for ``draft`` or ``active`` sessions.
- DELETE is allowed only for ``draft`` sessions (hard delete).
- ``time_now`` must be >= the highest ``time_now`` among all ``ended`` sessions.
- Participants: player must own the character_id; GM can register any.
- Character must exist and have ``detail_level = 'full'``.
- Duplicate participant registration (same character in same session) is rejected.
- PATCH contribution flag only allowed when session is in ``draft`` status.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.session import Session as SessionModel, SessionParticipant


def _max_ended_time_now(db: Session) -> int | None:
    """Return the highest ``time_now`` value among all ended sessions.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The maximum ``time_now`` of ended sessions, or ``None`` if no ended
        sessions exist or none have ``time_now`` set.
    """
    result = (
        db.query(SessionModel.time_now)
        .filter(
            SessionModel.status == "ended",
            SessionModel.time_now.is_not(None),
        )
        .order_by(SessionModel.time_now.desc())
        .first()
    )
    return result[0] if result else None


def validate_time_now(db: Session, time_now: int | None) -> str | None:
    """Validate that ``time_now`` does not go backwards relative to ended sessions.

    If ``time_now`` is ``None`` there is nothing to validate — returns ``None``.
    If there are no ended sessions with a ``time_now`` set, any value is valid.

    Args:
        db: Active SQLAlchemy session.
        time_now: The proposed Time Now value.

    Returns:
        An error message string if validation fails, or ``None`` if valid.
    """
    if time_now is None:
        return None

    max_ended = _max_ended_time_now(db)
    if max_ended is not None and time_now < max_ended:
        return (
            f"time_now must be >= the most recent ended session's time_now "
            f"({max_ended})"
        )
    return None


def create_session(
    db: Session,
    *,
    time_now: int | None = None,
    date: _dt.date | None = None,
    summary: str | None = None,
    notes: str | None = None,
) -> SessionModel:
    """Create a new Session with ``status = "draft"`` and persist it.

    Args:
        db: Active SQLAlchemy session.
        time_now: Optional abstract campaign time counter.
        date: Optional date for when the session takes/took place.
        summary: Optional session summary text.
        notes: Optional GM notes.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.session.Session`
        instance with its auto-generated ``id`` populated.
    """
    session = SessionModel(
        status="draft",
        time_now=time_now,
        date=date,
        summary=summary,
        notes=notes,
    )
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: str) -> SessionModel | None:
    """Retrieve a single Session by its ULID.

    Args:
        db: Active SQLAlchemy session.
        session_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.session.Session` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(SessionModel, session_id)


def list_sessions_query(db: Session) -> Any:
    """Build a SQLAlchemy query for the Sessions list.

    No filters are defined for sessions at this stage — the list returns all
    sessions.  The caller (``api.pagination.paginate``) adds ordering and
    LIMIT.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        A SQLAlchemy query targeting :class:`~wizards_engine.models.session.Session`.
    """
    return db.query(SessionModel)


def update_session(
    db: Session,
    session: SessionModel,
    updates: dict[str, Any],
) -> SessionModel:
    """Apply a partial update to *session* and persist it.

    Only keys present in *updates* are applied.  The caller is responsible for
    ensuring ``status`` checks have been performed before calling this function.

    Permitted fields: ``time_now``, ``date``, ``summary``, ``notes``.

    Args:
        db: Active SQLAlchemy session.
        session: The ORM instance to update.
        updates: Mapping of field names to new values.

    Returns:
        The updated :class:`~wizards_engine.models.session.Session` instance
        after flush.
    """
    for field, value in updates.items():
        setattr(session, field, value)
    db.flush()
    db.refresh(session)
    return session


def delete_session(db: Session, session: SessionModel) -> None:
    """Hard-delete *session* from the database.

    Sessions use hard delete (exception to the general soft-delete rule).
    Only ``draft`` sessions should be deleted — the caller must enforce this.

    Args:
        db: Active SQLAlchemy session.
        session: The ORM instance to hard-delete.
    """
    db.delete(session)
    db.flush()


# ---------------------------------------------------------------------------
# Session participant service functions
# ---------------------------------------------------------------------------


def get_character(db: Session, character_id: str) -> Character | None:
    """Retrieve a single Character by its ULID.

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.character.Character` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Character, character_id)


def get_participant(
    db: Session,
    session_id: str,
    character_id: str,
) -> SessionParticipant | None:
    """Retrieve a single SessionParticipant by the composite PK.

    Args:
        db: Active SQLAlchemy session.
        session_id: ULID of the session.
        character_id: ULID of the character.

    Returns:
        The :class:`~wizards_engine.models.session.SessionParticipant` if found,
        or ``None`` if no row exists with that composite key.
    """
    return db.get(SessionParticipant, (session_id, character_id))


def add_participant(
    db: Session,
    session: SessionModel,
    character_id: str,
    additional_contribution: bool = False,
) -> SessionParticipant:
    """Add a participant to *session* and persist it.

    Caller is responsible for ensuring:
    - The character exists and has ``detail_level = 'full'``.
    - The character is not already registered for this session.
    - The requesting player owns the character (unless GM).

    Args:
        db: Active SQLAlchemy session.
        session: The ORM instance of the session.
        character_id: ULID of the character to register.
        additional_contribution: Whether the participant checked the
            Additional Contribution flag.

    Returns:
        The newly created :class:`~wizards_engine.models.session.SessionParticipant`
        instance after flush.
    """
    participant = SessionParticipant(
        session_id=session.id,
        character_id=character_id,
        additional_contribution=additional_contribution,
    )
    db.add(participant)
    db.flush()
    db.refresh(participant)
    return participant


def remove_participant(
    db: Session,
    participant: SessionParticipant,
) -> None:
    """Remove *participant* from its session.

    No resource clawback is performed — the caller is responsible for
    enforcing that no resources need to be reversed.

    Args:
        db: Active SQLAlchemy session.
        participant: The ORM instance to delete.
    """
    db.delete(participant)
    db.flush()


def update_participant_contribution(
    db: Session,
    participant: SessionParticipant,
    additional_contribution: bool,
) -> SessionParticipant:
    """Update the ``additional_contribution`` flag on *participant*.

    Caller is responsible for ensuring the session is in ``draft`` status
    before calling this function.

    Args:
        db: Active SQLAlchemy session.
        participant: The ORM instance to update.
        additional_contribution: New value for the flag.

    Returns:
        The updated :class:`~wizards_engine.models.session.SessionParticipant`
        instance after flush.
    """
    participant.additional_contribution = additional_contribution
    db.flush()
    db.refresh(participant)
    return participant
