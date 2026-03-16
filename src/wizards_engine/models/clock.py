"""ORM model for Clock (progress trackers)."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from wizards_engine.models.base import Base, TimestampMixin


class Clock(TimestampMixin, Base):
    """A progress tracker attached to the narrative or to a Game Object.

    ``associated_type`` and ``associated_id`` are a polymorphic single-reference
    to a character, group, or location (no FK constraint — enforced in app code).

    ``is_completed`` is computed (``progress >= segments``) and not stored.
    Completion triggers auto-generation of a ``resolve_clock`` proposal.
    """

    __tablename__ = "clocks"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    segments: Mapped[int] = mapped_column(Integer, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Polymorphic single-ref (no FK — enforced in app code).
    associated_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    associated_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
