"""ORM model for the Character entity (unified PC + NPC)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class Character(TimestampMixin, Base):
    """Unified PC and NPC entity — the central Game Object for beings in the fiction.

    ``detail_level`` controls which mechanical columns are populated:

    - ``'full'`` (PC): stress, free_time, plot, gnosis, skills, magic_stats,
      last_session_time_now, plus 13 slots (2 core_trait + 3 role_trait + 8 pc_bond).
    - ``'simplified'`` (NPC): meter/skill/magic columns are null, 7 npc_bond slots.
    """

    __tablename__ = "characters"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_level: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'full' | 'simplified'
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Meter columns — full characters only (null for simplified).
    stress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gnosis: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # JSON stat blocks — full characters only.
    skills: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    magic_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    last_session_time_now: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships.
    user: Mapped[User] = relationship(
        "User",
        foreign_keys="[User.character_id]",
        primaryjoin="User.character_id == Character.id",
        uselist=False,
        back_populates="character",
    )
    magic_effects: Mapped[list[MagicEffect]] = relationship(
        "MagicEffect",
        back_populates="character",
        cascade="all, delete-orphan",
    )
