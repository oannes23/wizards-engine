"""ORM model for StarredObject (player's starred Game Objects feed)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base


class StarredObject(Base):
    """A user's starred Game Object preference entry.

    Composite PK: ``(user_id, object_type, object_id)``.
    No ULID and no timestamps — preference table only.
    Polymorphic ``object_type`` / ``object_id`` reference a character, group,
    or location (no FK constraint on object columns — enforced in app code).
    """

    __tablename__ = "starred_objects"

    user_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    object_type: Mapped[str] = mapped_column(
        String(20), primary_key=True, nullable=False
    )
    object_id: Mapped[str] = mapped_column(
        String(26), primary_key=True, nullable=False
    )

    # Relationship.
    user: Mapped[User] = relationship("User", foreign_keys="[StarredObject.user_id]")
