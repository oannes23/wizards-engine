"""ORM models for Story, StoryOwner, and StoryEntry."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class Story(TimestampMixin, Base):
    """A narrative thread in the campaign.

    Stories support sub-arc hierarchies via the self-referential ``parent_id``.
    Visibility is GM-controlled and derived from the unified visibility model.
    Default visibility is ``'familiar'``.
    """

    __tablename__ = "stories"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'active' | 'completed' | 'abandoned'
    parent_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("stories.id", ondelete="SET NULL"),
        nullable=True,
    )
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    visibility_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    visibility_overrides: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Self-referential relationships.
    parent: Mapped[Story | None] = relationship(
        "Story",
        foreign_keys="[Story.parent_id]",
        back_populates="children",
        remote_side="Story.id",
    )
    children: Mapped[list[Story]] = relationship(
        "Story",
        foreign_keys="[Story.parent_id]",
        back_populates="parent",
    )

    # Other relationships.
    entries: Mapped[list[StoryEntry]] = relationship(
        "StoryEntry",
        back_populates="story",
        cascade="all, delete-orphan",
    )
    owners: Mapped[list[StoryOwner]] = relationship(
        "StoryOwner",
        back_populates="story",
        cascade="all, delete-orphan",
    )


class StoryOwner(Base):
    """Association table — which Game Objects own a Story.

    Composite PK: ``(story_id, owner_type, owner_id)``.
    No ULID and no timestamps — association table only.
    Polymorphic ``owner_type`` / ``owner_id`` reference a character, group,
    or location (no FK constraint — enforced in app code).
    """

    __tablename__ = "story_owners"

    story_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    owner_type: Mapped[str] = mapped_column(
        String(20), primary_key=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(
        String(26), primary_key=True, nullable=False
    )

    # Relationship.
    story: Mapped[Story] = relationship("Story", back_populates="owners")


class StoryEntry(TimestampMixin, Base):
    """An individual narrative entry within a Story.

    Ordering is by ``created_at``.  Players may edit their own entries; the GM
    may edit any entry.  Soft-deleted rows are hidden from normal queries.
    """

    __tablename__ = "story_entries"

    story_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("stories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    character_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )
    game_object_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_by: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships.
    story: Mapped[Story] = relationship("Story", back_populates="entries")
    author: Mapped[User] = relationship(
        "User", foreign_keys="[StoryEntry.author_id]"
    )
    character: Mapped[Character | None] = relationship(
        "Character", foreign_keys="[StoryEntry.character_id]"
    )
    session: Mapped[Session | None] = relationship(
        "Session", foreign_keys="[StoryEntry.session_id]"
    )
