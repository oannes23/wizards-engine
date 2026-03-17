"""Service layer for Event creation (internal use only).

Events are the append-only audit trail for all state changes.  They are
never created via the API — always as side-effects of state-changing
operations.  This module owns event creation; other services call
``create_event`` when they mutate game state.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.

Key decisions:
- Session auto-capture: if no ``session_id`` is given and no
  ``parent_event_id`` is given, the active session (if any) is
  automatically tagged on the event.
- Rider events (``parent_event_id`` set) inherit ``session_id`` from
  their parent event.
- ``actor_type`` must be one of ``player``, ``gm``, ``system``.
- ``visibility`` must be one of the 7 canonical levels.
- All ``EventTarget`` rows are written in the same transaction as the
  ``Event`` row.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.session import Session as SessionModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ACTOR_TYPES: frozenset[str] = frozenset({"player", "gm", "system"})

VALID_VISIBILITY_LEVELS: frozenset[str] = frozenset(
    {"silent", "gm_only", "private", "bonded", "familiar", "public", "global"}
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_active_session_id(db: Session) -> str | None:
    """Return the ID of the currently active session, or ``None`` if absent.

    Queries the sessions table for a row with ``status = 'active'``.  The
    invariant that at most one active session exists at any time is enforced
    at the session service layer.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The ULID of the active session, or ``None`` if no active session
        exists.
    """
    result = db.execute(
        select(SessionModel.id).where(SessionModel.status == "active")
    ).first()
    return result[0] if result else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_event(
    db: Session,
    *,
    type: str,
    actor_type: str,
    actor_id: str | None = None,
    changes: dict[str, Any] | None = None,
    created_objects: list[dict[str, Any]] | None = None,
    deleted_objects: list[dict[str, Any]] | None = None,
    narrative: str | None = None,
    visibility: str = "public",
    targets: list[dict[str, Any]] | None = None,
    proposal_id: str | None = None,
    parent_event_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Event:
    """Create a new Event record with its associated EventTarget rows.

    All rows are written in a single transaction (flush).  The caller is
    responsible for committing.

    Session ID resolution order:
    1. If ``session_id`` is explicitly provided, use it.
    2. If ``parent_event_id`` is provided, inherit ``session_id`` from the
       parent event.
    3. Otherwise, auto-capture the currently active session's ID (if any).

    Args:
        db: Active SQLAlchemy session.
        type: Convention-based ``{domain}.{action}`` string (e.g.
            ``character.stress_changed``).
        actor_type: One of ``player``, ``gm``, or ``system``.
        actor_id: FK to ``users.id`` — ``None`` for system-generated events.
        changes: Mapping of fully-qualified change keys
            ``{type}.{id}.{field}`` to ``{op, before, after, clamped?}``
            dicts.  Op is one of ``field.set``, ``meter.delta``,
            ``meter.set``.  Defaults to an empty dict.
        created_objects: List of ``{type, id}`` dicts for objects created
            as part of this event.
        deleted_objects: List of ``{type, id}`` dicts for objects
            soft-deleted as part of this event.
        narrative: Optional human-readable description of the event.
        visibility: One of the 7 canonical visibility levels — ``silent``,
            ``gm_only``, ``private``, ``bonded``, ``familiar``, ``public``,
            ``global``.  Defaults to ``public``.
        targets: List of ``{target_type, target_id, is_primary}`` dicts.
            Each entry is written as an ``EventTarget`` row.
        proposal_id: Optional FK to the ``proposals`` table for events
            that result from a GM-approved proposal.
        parent_event_id: Optional FK to a parent ``events`` row.  When
            provided the event is a *rider event* and inherits the parent's
            ``session_id`` unless ``session_id`` is explicitly supplied.
        session_id: Explicit session ID.  When omitted the service
            resolves the correct value via the rules above.
        metadata: Optional freeform JSON stored in the ``metadata`` column.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.event.Event`
        instance with its ``targets`` relationship populated.

    Raises:
        ValueError: If ``actor_type`` is not one of the three valid values.
        ValueError: If ``visibility`` is not one of the 7 valid levels.
    """
    if actor_type not in VALID_ACTOR_TYPES:
        raise ValueError(
            f"Invalid actor_type '{actor_type}'. "
            f"Must be one of: {sorted(VALID_ACTOR_TYPES)}."
        )

    if visibility not in VALID_VISIBILITY_LEVELS:
        raise ValueError(
            f"Invalid visibility '{visibility}'. "
            f"Must be one of: {sorted(VALID_VISIBILITY_LEVELS)}."
        )

    # Resolve session_id.
    resolved_session_id: str | None = session_id
    if resolved_session_id is None:
        if parent_event_id is not None:
            # Rider event: inherit session_id from parent.
            parent = db.get(Event, parent_event_id)
            if parent is not None:
                resolved_session_id = parent.session_id
        else:
            # Auto-capture the active session.
            resolved_session_id = _get_active_session_id(db)

    event = Event(
        type=type,
        actor_type=actor_type,
        actor_id=actor_id,
        changes=changes if changes is not None else {},
        created_objects=created_objects,
        deleted_objects=deleted_objects,
        narrative=narrative,
        visibility=visibility,
        proposal_id=proposal_id,
        parent_event_id=parent_event_id,
        session_id=resolved_session_id,
        metadata_=metadata,
    )
    db.add(event)
    db.flush()  # populate event.id before creating EventTarget rows

    if targets:
        for target_spec in targets:
            event_target = EventTarget(
                event_id=event.id,
                target_type=target_spec["target_type"],
                target_id=target_spec["target_id"],
                is_primary=target_spec.get("is_primary", False),
            )
            db.add(event_target)
        db.flush()

    db.refresh(event)
    return event
