"""ORM models for Session and SessionParticipant."""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text

date_type = _dt.date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class Session(TimestampMixin, Base):
    """A play-session record.

    Lifecycle: ``draft`` → ``active`` → ``ended`` (forward-only).
    Only one ``active`` session may exist at a time (enforced in app code).
    Draft sessions may be hard-deleted; active/ended sessions are permanent.
    """

    __tablename__ = "sessions"

    status: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 'draft' | 'active' | 'ended'
    time_now: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships.
    participants: Mapped[list[SessionParticipant]] = relationship(
        "SessionParticipant",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class SessionParticipant(Base):
    """Association table — which characters are registered for a session.

    Composite PK: ``(session_id, character_id)``.
    No ULID and no timestamps — join-table only.
    """

    __tablename__ = "session_participants"

    session_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    character_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    additional_contribution: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Relationships.
    session: Mapped[Session] = relationship("Session", back_populates="participants")
    character: Mapped[Character] = relationship("Character")

    @property
    def character_name(self) -> str | None:
        """Return the linked Character's name, or None if not loaded."""
        if self.character is not None:
            return self.character.name
        return None
