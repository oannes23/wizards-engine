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
- Only one ``active`` session may exist at a time (enforced in ``start_session``).
- ``time_now`` must be set before starting a session (required for FT distribution).
- Late joins: adding a participant to an ``active`` session triggers immediate
  FT + Plot distribution for that participant only (``distribute_to_participant``).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.session import Session as SessionModel, SessionParticipant
from wizards_engine.services.proposal.constants import FREE_TIME_MAX, PLOT_MAX

__all__ = [
    "validate_time_now",
    "create_session",
    "get_session",
    "list_sessions_query",
    "update_session",
    "delete_session",
    "get_character",
    "get_participant",
    "add_participant",
    "remove_participant",
    "get_active_session",
    "start_session",
    "distribute_to_participant",
    "end_session",
    "update_participant_contribution",
]

# FT cap constant — free_time cannot exceed this value.
_FT_CAP = FREE_TIME_MAX

# Plot cap constant — plot is clamped to this value at session end.
_PLOT_CAP = PLOT_MAX


def _max_ended_time_now(db: Session) -> int | None:
    """Return the highest ``time_now`` value among all ended sessions.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The maximum ``time_now`` of ended sessions, or ``None`` if no ended
        sessions exist or none have ``time_now`` set.
    """
    result = db.execute(
        select(SessionModel.time_now)
        .where(
            SessionModel.status == "ended",
            SessionModel.time_now.is_not(None),
        )
        .order_by(SessionModel.time_now.desc())
    ).first()
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
    """Build a SQLAlchemy select statement for the Sessions list.

    No filters are defined for sessions at this stage — the list returns all
    sessions.  The caller (``api.pagination.paginate``) adds ordering and
    LIMIT.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        A SQLAlchemy ``Select`` statement targeting :class:`~wizards_engine.models.session.Session`.
    """
    return select(SessionModel)


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


def get_active_session(db: Session) -> SessionModel | None:
    """Return the currently active session, or ``None`` if none exists.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The :class:`~wizards_engine.models.session.Session` with
        ``status = "active"``, or ``None`` if no such session exists.
    """
    return db.scalars(
        select(SessionModel).where(SessionModel.status == "active")
    ).first()


def start_session(db: Session, session: SessionModel) -> SessionModel:
    """Transition *session* from ``draft`` to ``active`` and distribute resources.

    This is the full Session Start operation:

    1. Validates ``session.status == "draft"`` — raises ``ValueError`` otherwise.
    2. Enforces one active session at a time — raises ``ValueError`` if one exists.
    3. Validates ``session.time_now`` is set — raises ``ValueError`` if ``None``.
    4. Transitions status to ``"active"``.
    5. For each participant:
       - FT distribution: ``ft_gained = session.time_now - character.last_session_time_now``.
         Added to ``character.free_time``, capped at 20.
         Updates ``character.last_session_time_now`` to ``session.time_now``.
       - Plot distribution: +1 (or +2 if ``additional_contribution = True``).
         Plot may overflow above 5.
    6. Contribution flags are locked (session status change to ``active``
       prevents further PATCH updates via the route handler's draft-only check).
    7. Creates 3 events in the same transaction:
       - ``session.started`` (global)
       - ``session.ft_distributed`` (silent)
       - ``session.plot_distributed`` (silent)
       All events have ``actor_type = "system"`` and ``session_id = session.id``.

    The caller is responsible for committing the transaction.

    Args:
        db: Active SQLAlchemy session.
        session: The ORM instance to start.  Must be in ``draft`` status.

    Returns:
        The updated :class:`~wizards_engine.models.session.Session` instance
        after all mutations and event creation.

    Raises:
        ValueError: If the session is not in ``draft`` status.
        ValueError: If another session is already ``active``.
        ValueError: If ``session.time_now`` is not set.
    """
    # --- Import here to avoid circular imports (event service imports session model) ---
    from wizards_engine.services.event import create_event  # noqa: PLC0415

    if session.status != "draft":
        raise ValueError(
            f"Session is not in draft status (current status: '{session.status}')."
        )

    existing_active = get_active_session(db)
    if existing_active is not None:
        raise ValueError(
            f"Another session ('{existing_active.id}') is already active."
        )

    if session.time_now is None:
        raise ValueError(
            "Session must have time_now set before it can be started."
        )

    error = validate_time_now(db, session.time_now)
    if error:
        raise ValueError(error)

    # Ensure participants are loaded before we start mutating.
    participants = session.participants  # accesses the relationship

    # ------------------------------------------------------------------
    # Capture before-values for all character changes BEFORE any mutation.
    # ------------------------------------------------------------------
    ft_before: dict[str, int] = {}
    last_time_before: dict[str, int] = {}
    plot_before: dict[str, int] = {}

    for p in participants:
        char = p.character
        ft_before[char.id] = char.free_time or 0
        last_time_before[char.id] = char.last_session_time_now or 0
        plot_before[char.id] = char.plot or 0

    # ------------------------------------------------------------------
    # Transition session status.
    # ------------------------------------------------------------------
    session.status = "active"
    db.flush()

    # ------------------------------------------------------------------
    # Distribute FT and Plot for each participant.
    # ------------------------------------------------------------------
    ft_after: dict[str, int] = {}
    last_time_after: dict[str, int] = {}
    ft_clamped: dict[str, bool] = {}
    plot_after: dict[str, int] = {}

    for p in participants:
        char = p.character

        # FT distribution.
        ft_delta = session.time_now - last_time_before[char.id]
        new_ft = ft_before[char.id] + ft_delta
        clamped = new_ft > _FT_CAP
        new_ft = min(new_ft, _FT_CAP)
        char.free_time = new_ft
        char.last_session_time_now = session.time_now

        ft_after[char.id] = new_ft
        last_time_after[char.id] = session.time_now
        ft_clamped[char.id] = clamped

        # Plot distribution.
        plot_delta = 2 if p.additional_contribution else 1
        new_plot = plot_before[char.id] + plot_delta
        char.plot = new_plot
        plot_after[char.id] = new_plot

    db.flush()

    # ------------------------------------------------------------------
    # Build event changes payloads.
    # ------------------------------------------------------------------
    started_changes: dict[str, Any] = {
        f"session.{session.id}.status": {
            "op": "field.set",
            "before": "draft",
            "after": "active",
        }
    }

    ft_changes: dict[str, Any] = {}
    for p in participants:
        char_id = p.character_id
        ft_entry: dict[str, Any] = {
            "op": "meter.delta",
            "before": ft_before[char_id],
            "after": ft_after[char_id],
        }
        if ft_clamped[char_id]:
            ft_entry["clamped"] = True
        ft_changes[f"character.{char_id}.free_time"] = ft_entry
        ft_changes[f"character.{char_id}.last_session_time_now"] = {
            "op": "field.set",
            "before": last_time_before[char_id],
            "after": last_time_after[char_id],
        }

    plot_changes: dict[str, Any] = {}
    for p in participants:
        char_id = p.character_id
        plot_changes[f"character.{char_id}.plot"] = {
            "op": "meter.delta",
            "before": plot_before[char_id],
            "after": plot_after[char_id],
        }

    # ------------------------------------------------------------------
    # Create 3 events (all tagged to this session explicitly).
    # ------------------------------------------------------------------
    create_event(
        db,
        type="session.started",
        actor_type="system",
        actor_id=None,
        changes=started_changes,
        narrative="Session started.",
        visibility="global",
        targets=None,
        session_id=session.id,
    )

    create_event(
        db,
        type="session.ft_distributed",
        actor_type="system",
        actor_id=None,
        changes=ft_changes,
        visibility="silent",
        targets=None,
        session_id=session.id,
    )

    create_event(
        db,
        type="session.plot_distributed",
        actor_type="system",
        actor_id=None,
        changes=plot_changes,
        visibility="silent",
        targets=None,
        session_id=session.id,
    )

    db.refresh(session)
    return session


def distribute_to_participant(
    db: Session,
    session: SessionModel,
    character: Character,
    additional_contribution: bool,
    actor_type: str,
    actor_id: str | None,
) -> dict[str, Any]:
    """Distribute FT and Plot to a single late-joining participant.

    Called when a character is added to an **active** session via
    ``POST /sessions/{id}/participants``.  Applies the same distribution
    formula as ``start_session``:

    - FT: ``ft_gained = session.time_now - character.last_session_time_now``.
      Added to ``character.free_time``, capped at :data:`_FT_CAP`.
      Updates ``character.last_session_time_now`` to ``session.time_now``.
    - Plot: +1 (or +2 if ``additional_contribution = True``).  Plot may
      overflow above 5.

    Creates a single ``session.participant_added`` event (visibility:
    ``global``) recording the FT, ``last_session_time_now``, and Plot
    changes.  The character is listed as the primary target.

    The caller is responsible for committing the transaction.

    Args:
        db: Active SQLAlchemy session.
        session: The ORM instance of the active session.  Must have
            ``time_now`` set.
        character: The character being added as a late participant.
        additional_contribution: Whether the participant checked the
            Additional Contribution flag (+2 Plot instead of +1).
        actor_type: ``"player"`` or ``"gm"`` — identifies who triggered
            the add.
        actor_id: FK to ``users.id`` of the user who triggered the add.

    Returns:
        A dict with keys ``ft_gained``, ``ft_after``, ``ft_clamped``,
        ``plot_gained``, ``plot_after`` summarising the distribution.
    """
    from wizards_engine.services.event import create_event  # noqa: PLC0415

    time_now = session.time_now  # guaranteed non-None for active sessions

    # Capture before-values.
    ft_before = character.free_time or 0
    last_time_before = character.last_session_time_now or 0
    plot_before = character.plot or 0

    # ------------------------------------------------------------------
    # Compute and apply FT distribution.
    # ------------------------------------------------------------------
    ft_delta = time_now - last_time_before
    new_ft = ft_before + ft_delta
    clamped = new_ft > _FT_CAP
    new_ft = min(new_ft, _FT_CAP)
    character.free_time = new_ft
    character.last_session_time_now = time_now

    # ------------------------------------------------------------------
    # Compute and apply Plot distribution.
    # ------------------------------------------------------------------
    plot_delta = 2 if additional_contribution else 1
    new_plot = plot_before + plot_delta
    character.plot = new_plot

    db.flush()

    # ------------------------------------------------------------------
    # Build event changes payload.
    # ------------------------------------------------------------------
    char_id = character.id

    ft_entry: dict[str, Any] = {
        "op": "meter.delta",
        "before": ft_before,
        "after": new_ft,
    }
    if clamped:
        ft_entry["clamped"] = True

    changes: dict[str, Any] = {
        f"character.{char_id}.free_time": ft_entry,
        f"character.{char_id}.last_session_time_now": {
            "op": "field.set",
            "before": last_time_before,
            "after": time_now,
        },
        f"character.{char_id}.plot": {
            "op": "meter.delta",
            "before": plot_before,
            "after": new_plot,
        },
    }

    # ------------------------------------------------------------------
    # Create the participant_added event.
    # ------------------------------------------------------------------
    create_event(
        db,
        type="session.participant_added",
        actor_type=actor_type,
        actor_id=actor_id,
        changes=changes,
        narrative=f"{character.name} joined the session.",
        visibility="global",
        targets=[
            {
                "target_type": "character",
                "target_id": char_id,
                "is_primary": True,
            }
        ],
        session_id=session.id,
    )

    return {
        "ft_gained": ft_delta,
        "ft_after": new_ft,
        "ft_clamped": clamped,
        "plot_gained": plot_delta,
        "plot_after": new_plot,
    }


def end_session(db: Session, session: SessionModel) -> SessionModel:
    """Transition *session* from ``active`` to ``ended`` and clamp participant Plot.

    This is the full Session End operation:

    1. Validates ``session.status == "active"`` — raises ``ValueError`` otherwise.
    2. Transitions status to ``"ended"``.
    3. For each participant, if ``character.plot > 5``, sets it to 5 (excess lost).
    4. Creates one event:
       - ``session.ended`` (global), actor_type ``system``, actor_id ``None``.
         Changes include the session status transition and any Plot clamp changes.

    The caller is responsible for committing the transaction.

    Args:
        db: Active SQLAlchemy session.
        session: The ORM instance to end.  Must be in ``active`` status.

    Returns:
        The updated :class:`~wizards_engine.models.session.Session` instance
        after all mutations and event creation.

    Raises:
        ValueError: If the session is not in ``active`` status.
    """
    # --- Import here to avoid circular imports (event service imports session model) ---
    from wizards_engine.services.event import create_event  # noqa: PLC0415

    if session.status != "active":
        raise ValueError(
            f"Session is not in active status (current status: '{session.status}')."
        )

    # Ensure participants are loaded before mutating.
    participants = session.participants

    # ------------------------------------------------------------------
    # Capture before-values for Plot BEFORE any mutation.
    # ------------------------------------------------------------------
    plot_before: dict[str, int] = {}
    for p in participants:
        plot_before[p.character_id] = p.character.plot or 0

    # ------------------------------------------------------------------
    # Transition session status.
    # ------------------------------------------------------------------
    session.status = "ended"
    db.flush()

    # ------------------------------------------------------------------
    # Clamp Plot to 5 for each participant.
    # ------------------------------------------------------------------
    plot_after: dict[str, int] = {}
    plot_clamped: dict[str, bool] = {}

    for p in participants:
        char = p.character
        before = plot_before[p.character_id]
        if before > _PLOT_CAP:
            char.plot = _PLOT_CAP
            plot_after[p.character_id] = _PLOT_CAP
            plot_clamped[p.character_id] = True
        else:
            plot_after[p.character_id] = before
            plot_clamped[p.character_id] = False

    db.flush()

    # ------------------------------------------------------------------
    # Build the event changes payload.
    # ------------------------------------------------------------------
    ended_changes: dict[str, Any] = {
        f"session.{session.id}.status": {
            "op": "field.set",
            "before": "active",
            "after": "ended",
        }
    }

    for p in participants:
        char_id = p.character_id
        if plot_clamped[char_id]:
            ended_changes[f"character.{char_id}.plot"] = {
                "op": "meter.set",
                "before": plot_before[char_id],
                "after": plot_after[char_id],
                "clamped": True,
            }

    # ------------------------------------------------------------------
    # Create 1 event tagged to this session.
    # ------------------------------------------------------------------
    create_event(
        db,
        type="session.ended",
        actor_type="system",
        actor_id=None,
        changes=ended_changes,
        narrative="Session ended.",
        visibility="global",
        targets=None,
        session_id=session.id,
    )

    db.refresh(session)
    return session


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
