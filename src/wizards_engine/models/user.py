"""ORM models for authentication entities: User and Invite."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin, _new_ulid, _utcnow


class User(TimestampMixin, Base):
    """A player or GM account.

    The GM is a User with ``role = 'gm'``.  The ``character_id`` FK is null
    for the GM (unless the GM is also a player) and unique for players
    (1-to-1 player-character mapping).
    """

    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # 'gm' | 'player' | 'viewer'
    login_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    character_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationship — navigates to the linked Character (if any).
    character: Mapped[Character] = relationship(
        "Character",
        foreign_keys="[User.character_id]",
        primaryjoin="User.character_id == Character.id",
        uselist=False,
        back_populates="user",
    )


class Invite(Base):
    """Single-use invite code.

    The invite ``id`` (a ULID) IS the shareable code — there is no separate
    ``code`` column.  Bare invites are not pre-linked to a character; the
    character is created during redemption.

    Note: ``Invite`` has only ``created_at`` — no ``updated_at``.  It does not
    inherit ``TimestampMixin`` so that only the necessary columns are present.
    """

    __tablename__ = "invites"

    id: Mapped[str] = mapped_column(
        String(26),
        primary_key=True,
        default=_new_ulid,
        nullable=False,
    )
    is_consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="player")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
