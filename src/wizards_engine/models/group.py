"""ORM model for the Group entity (organizations, crews, guilds, etc.)."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from wizards_engine.models.base import Base, TimestampMixin


class Group(TimestampMixin, Base):
    """An organization or faction — a Game Object.

    Slot counts (stored in the ``slots`` table):
    - 10 ``group_trait`` slots
    - 7 ``group_relation`` slots (FK → other Groups)
    - Unlimited ``group_holding`` slots (FK → Locations)

    ``members`` are derived by querying ``slots`` for bonds targeting this Group.
    """

    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
