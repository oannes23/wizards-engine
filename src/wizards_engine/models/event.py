"""ORM models for Event and EventTarget (append-only event log)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, _new_ulid, _utcnow


class Event(Base):
    """An immutable record of a state change (append-only log entry).

    Events are never modified or deleted, except ``visibility`` (GM override).
    The ``metadata_`` Python attribute maps to a ``metadata`` column in the DB
    to avoid conflicting with SQLAlchemy's reserved ``metadata`` attribute.

    Events have only ``created_at`` — no ``updated_at``.  They do NOT inherit
    ``TimestampMixin``.
    """

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(
        String(26),
        primary_key=True,
        default=_new_ulid,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 'player' | 'gm' | 'system'
    actor_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_objects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    deleted_objects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    proposal_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("proposals.id", ondelete="SET NULL", use_alter=True, name="fk_events_proposal_id"),
        nullable=True,
        index=True,
    )
    parent_event_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 'metadata' is a reserved name on SQLAlchemy's DeclarativeBase; map via column name.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships.
    actor: Mapped[User | None] = relationship(
        "User", foreign_keys="[Event.actor_id]"
    )
    targets: Mapped[list[EventTarget]] = relationship(
        "EventTarget",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    parent_event: Mapped[Event | None] = relationship(
        "Event",
        foreign_keys="[Event.parent_event_id]",
        back_populates="rider_events",
        remote_side="Event.id",
    )
    rider_events: Mapped[list[Event]] = relationship(
        "Event",
        foreign_keys="[Event.parent_event_id]",
        back_populates="parent_event",
    )
    session: Mapped[Session | None] = relationship(
        "Session", foreign_keys="[Event.session_id]"
    )


class EventTarget(Base):
    """Association table — which Game Objects are affected by an Event.

    Composite PK: ``(event_id, target_type, target_id)``.
    No ULID and no timestamps — association table only.
    Polymorphic ``target_type`` / ``target_id`` (no FK — enforced in app code).
    """

    __tablename__ = "event_targets"
    __table_args__ = (
        # Composite index for efficient reverse lookups: "recent events for entity X"
        Index("ix_event_targets_target", "target_type", "target_id"),
    )

    event_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(
        String(20), primary_key=True, nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        String(26), primary_key=True, nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship.
    event: Mapped[Event] = relationship("Event", back_populates="targets")
