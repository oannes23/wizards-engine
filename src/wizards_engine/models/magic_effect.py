"""ORM model for MagicEffect (magical effects on a character's sheet)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class MagicEffect(TimestampMixin, Base):
    """A magical effect recorded on a character's sheet.

    ``effect_type`` is one of ``'instant'``, ``'charged'``, or ``'permanent'``.
    Charged effects use ``charges_current`` and ``charges_max``; instant and
    permanent effects leave those columns null.

    Business constraint (enforced in application code): max 9 active effects
    per character (charged + permanent; instants do not count toward the cap).
    """

    __tablename__ = "magic_effects"

    character_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    effect_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'instant' | 'charged' | 'permanent'
    power_level: Mapped[int] = mapped_column(Integer, nullable=False)
    charges_current: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charges_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    character: Mapped[Character] = relationship(
        "Character",
        back_populates="magic_effects",
    )
