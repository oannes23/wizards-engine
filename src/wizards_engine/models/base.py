"""Declarative base and shared mixins for all SQLAlchemy ORM models.

All models should inherit from ``Base`` (for the declarative base) and
``TimestampMixin`` for standard ``id``, ``created_at``, and ``updated_at``
columns.

Example::

    from wizards_engine.models.base import Base, TimestampMixin

    class Character(TimestampMixin, Base):
        __tablename__ = "characters"
        name: Mapped[str] = mapped_column(String(100), nullable=False)
"""

import ulid as _ulid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def _new_ulid() -> str:
    """Generate a new ULID string (26 ASCII characters, sortable by time)."""
    return str(_ulid.ULID())


class Base(DeclarativeBase):
    """SQLAlchemy 2.0-style declarative base for all Wizards Engine models."""


class TimestampMixin:
    """Mixin that adds a ULID primary key and auto-managed timestamps.

    Columns
    -------
    id
        ULID stored as TEXT(26). Auto-generated on creation.
        Sorting by ``id`` approximates sorting by creation time.
    created_at
        UTC datetime set once when the row is first inserted.
    updated_at
        UTC datetime updated automatically on every flush that modifies the row.
    """

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

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
