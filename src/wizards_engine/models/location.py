"""ORM model for the Location entity (places in the game world)."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class Location(TimestampMixin, Base):
    """A place in the game world — a Game Object.

    Locations are nestable: ``parent_id`` creates an unlimited-depth hierarchy.

    Slot counts (stored in the ``slots`` table):
    - 5 ``feature_trait`` slots
    - Unlimited ``location_bond`` slots
    """

    __tablename__ = "locations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Self-referential relationships.
    parent: Mapped["Location | None"] = relationship(
        "Location",
        foreign_keys=[parent_id],
        back_populates="children",
        remote_side="Location.id",
    )
    children: Mapped[list["Location"]] = relationship(
        "Location",
        foreign_keys=[parent_id],
        back_populates="parent",
    )
