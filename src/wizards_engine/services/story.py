"""Service layer for Story CRUD operations and owners sub-resource.

All database interactions for the Story resource live here.  Route
handlers call these functions and handle HTTP-level concerns (status codes,
response shaping) separately.

Functions are stateless — each accepts a SQLAlchemy ``Session`` as its
first argument.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import exists, literal, select, text as sa_text
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.session import Session as GameSession
from wizards_engine.models.story import Story, StoryEntry, StoryOwner

__all__ = [
    "create_story",
    "get_story",
    "list_stories_query",
    "update_story",
    "delete_story",
    "get_game_object",
    "add_owner",
    "get_owner",
    "remove_owner",
    "get_story_entries",
    "get_active_session_id",
    "create_story_entry",
    "get_story_entry",
    "update_story_entry",
    "delete_story_entry",
]


# ---------------------------------------------------------------------------
# Owner type → model class mapping
# ---------------------------------------------------------------------------

_OWNER_MODEL_MAP: dict[str, type] = {
    "character": Character,
    "group": Group,
    "location": Location,
}


# ---------------------------------------------------------------------------
# Story CRUD
# ---------------------------------------------------------------------------


def create_story(
    db: Session,
    *,
    name: str,
    summary: str | None = None,
    status: str = "active",
    parent_id: str | None = None,
    tags: list[str] | None = None,
) -> Story:
    """Create a new Story and persist it.

    Args:
        db: Active SQLAlchemy session.
        name: Story name.  Must be non-empty (caller validates).
        summary: Optional narrative summary.
        status: One of ``active``, ``completed``, ``abandoned``.  Defaults to ``active``.
        parent_id: Optional ULID of a parent Story.  Caller validates existence.
        tags: Optional list of freeform tag strings.

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.story.Story`
        instance with its auto-generated ``id`` populated.
    """
    story = Story(
        name=name,
        summary=summary,
        status=status,
        parent_id=parent_id,
        tags=tags,
        is_deleted=False,
    )
    db.add(story)
    db.flush()
    db.refresh(story)
    return story


def get_story(db: Session, story_id: str) -> Story | None:
    """Retrieve a single Story by its ULID, including soft-deleted ones.

    Args:
        db: Active SQLAlchemy session.
        story_id: ULID primary key.

    Returns:
        The :class:`~wizards_engine.models.story.Story` if found,
        or ``None`` if no row exists with that ID.
    """
    return db.get(Story, story_id)


_ALLOWED_SORT_COLS_STORY = {
    "name": Story.name,
    "created_at": Story.created_at,
    "updated_at": Story.updated_at,
}


def list_stories_query(
    db: Session,
    *,
    status: str | None = None,
    tag: str | None = None,
    owner_type: str | None = None,
    owner_id: str | None = None,
    include_deleted: bool = False,
    sort_by: str = "name",
    sort_dir: str = "asc",
):
    """Build a SQLAlchemy select statement for the Stories list with optional filters.

    The returned statement has no ``ORDER BY`` or ``LIMIT`` applied — the
    caller (``api.pagination.paginate``) adds those.

    Args:
        db: Active SQLAlchemy session.
        status: Filter to stories with this status (``active``, ``completed``, or ``abandoned``).
        tag: Filter to stories that include this exact string in their ``tags`` JSON array.
        owner_type: Owner type for the ``?owner=<type>:<id>`` filter.
        owner_id: Owner ID for the ``?owner=<type>:<id>`` filter.  Must be paired with ``owner_type``.
        include_deleted: When ``True``, include soft-deleted stories.  Defaults to ``False``.
        sort_by: Column to sort by — ``"name"``, ``"created_at"``, or ``"updated_at"``.
            Defaults to ``"name"``.
        sort_dir: Sort direction — ``"asc"`` or ``"desc"``.  Defaults to ``"asc"``.

    Returns:
        A 2-tuple of ``(Select statement, order_by expression)`` targeting
        :class:`~wizards_engine.models.story.Story`.
    """
    stmt = select(Story)

    if not include_deleted:
        stmt = stmt.where(Story.is_deleted.is_(False))

    if status is not None:
        stmt = stmt.where(Story.status == status)

    if tag is not None:
        # Use SQLite's json_each() to check for exact tag membership.
        # The subquery correlates to the outer stories table via the alias.
        tag_subq = (
            select(literal(1))
            .select_from(sa_text("json_each(stories.tags)"))
            .where(sa_text("json_each.value = :tag_val"))
            .correlate_except()
        )
        stmt = stmt.where(exists(tag_subq).params(tag_val=tag))

    if owner_type is not None and owner_id is not None:
        stmt = stmt.join(
            StoryOwner,
            (StoryOwner.story_id == Story.id)
            & (StoryOwner.owner_type == owner_type)
            & (StoryOwner.owner_id == owner_id),
        )

    sort_col = _ALLOWED_SORT_COLS_STORY.get(sort_by, Story.name)
    return stmt, sort_col, sort_dir


def update_story(
    db: Session,
    story: Story,
    updates: dict[str, Any],
) -> Story:
    """Apply a partial update to *story* and persist it.

    Only keys present in *updates* are applied.  The caller (route handler)
    is responsible for building *updates* using ``model_fields_set`` so that
    omitted PATCH fields are not overwritten.

    Args:
        db: Active SQLAlchemy session.
        story: The ORM instance to update.
        updates: Mapping of field names to new values.

    Returns:
        The updated :class:`~wizards_engine.models.story.Story` instance after flush.
    """
    for field, value in updates.items():
        setattr(story, field, value)
    db.flush()
    db.refresh(story)
    return story


def delete_story(db: Session, story: Story) -> None:
    """Soft-delete *story* by setting ``is_deleted = True``.

    Args:
        db: Active SQLAlchemy session.
        story: The ORM instance to soft-delete.
    """
    story.is_deleted = True
    db.flush()


# ---------------------------------------------------------------------------
# Owners sub-resource
# ---------------------------------------------------------------------------


def get_game_object(db: Session, owner_type: str, owner_id: str) -> Any | None:
    """Retrieve a Game Object (Character, Group, or Location) by type and ID.

    Used to validate that an owner reference exists before adding it.

    Args:
        db: Active SQLAlchemy session.
        owner_type: One of ``character``, ``group``, or ``location``.
        owner_id: ULID of the Game Object.

    Returns:
        The ORM instance if found, or ``None``.
    """
    model_cls = _OWNER_MODEL_MAP.get(owner_type)
    if model_cls is None:
        return None
    return db.get(model_cls, owner_id)


def add_owner(
    db: Session,
    story: Story,
    owner_type: str,
    owner_id: str,
) -> StoryOwner:
    """Add a Game Object as an owner of *story*.

    Does not check for duplicate owners — the composite PK (story_id,
    owner_type, owner_id) will raise a DB-level IntegrityError on duplicate.

    Args:
        db: Active SQLAlchemy session.
        story: The Story to add an owner to.
        owner_type: One of ``character``, ``group``, or ``location``.
        owner_id: ULID of the owning Game Object.

    Returns:
        The newly created :class:`~wizards_engine.models.story.StoryOwner` instance.
    """
    owner_record = StoryOwner(
        story_id=story.id,
        owner_type=owner_type,
        owner_id=owner_id,
    )
    db.add(owner_record)
    db.flush()
    return owner_record


def get_owner(
    db: Session,
    story_id: str,
    owner_type: str,
    owner_id: str,
) -> StoryOwner | None:
    """Retrieve a specific owner record by its composite key.

    Args:
        db: Active SQLAlchemy session.
        story_id: ULID of the Story.
        owner_type: One of ``character``, ``group``, or ``location``.
        owner_id: ULID of the owning Game Object.

    Returns:
        The :class:`~wizards_engine.models.story.StoryOwner` if found, or ``None``.
    """
    return db.get(StoryOwner, (story_id, owner_type, owner_id))


def remove_owner(db: Session, owner_record: StoryOwner) -> None:
    """Remove a story owner record.

    Args:
        db: Active SQLAlchemy session.
        owner_record: The :class:`~wizards_engine.models.story.StoryOwner` to delete.
    """
    db.delete(owner_record)
    db.flush()


# ---------------------------------------------------------------------------
# Detail — entries for the story detail endpoint
# ---------------------------------------------------------------------------


def get_story_entries(db: Session, story_id: str) -> list[StoryEntry]:
    """Return all non-deleted entries for a Story, sorted by ``created_at`` ascending.

    Args:
        db: Active SQLAlchemy session.
        story_id: ULID of the Story.

    Returns:
        List of :class:`~wizards_engine.models.story.StoryEntry` instances.
    """
    return db.scalars(
        select(StoryEntry)
        .where(StoryEntry.story_id == story_id, StoryEntry.is_deleted.is_(False))
        .order_by(StoryEntry.created_at.asc())
    ).all()


# ---------------------------------------------------------------------------
# Entries sub-resource
# ---------------------------------------------------------------------------


def get_active_session_id(db: Session) -> str | None:
    """Return the ID of the currently active Session, if any.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        The ULID of the active :class:`~wizards_engine.models.session.Session`,
        or ``None`` if no session is currently active.
    """
    active = db.scalars(
        select(GameSession).where(GameSession.status == "active")
    ).first()
    return active.id if active is not None else None


def create_story_entry(
    db: Session,
    *,
    story_id: str,
    text: str,
    author_id: str,
    character_id: str | None = None,
    game_object_refs: list[dict[str, str]] | None = None,
    session_id: str | None = None,
) -> StoryEntry:
    """Create a new narrative entry within a Story.

    Args:
        db: Active SQLAlchemy session.
        story_id: ULID of the containing Story.
        text: Narrative content.
        author_id: ULID of the User creating the entry.
        character_id: Optional ULID of a linked Character.
        game_object_refs: Optional list of ``{type, id}`` Game Object references.
        session_id: Optional ULID of the active session (auto-captured by caller).

    Returns:
        The newly created and flushed :class:`~wizards_engine.models.story.StoryEntry`.
    """
    entry = StoryEntry(
        story_id=story_id,
        text=text,
        author_id=author_id,
        character_id=character_id,
        session_id=session_id,
        game_object_refs=game_object_refs,
        is_deleted=False,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


def get_story_entry(db: Session, entry_id: str) -> StoryEntry | None:
    """Retrieve a single StoryEntry by its ULID.

    Args:
        db: Active SQLAlchemy session.
        entry_id: ULID primary key of the entry.

    Returns:
        The :class:`~wizards_engine.models.story.StoryEntry` if found, or ``None``.
    """
    return db.get(StoryEntry, entry_id)


def update_story_entry(
    db: Session,
    entry: StoryEntry,
    *,
    text: str,
    updated_by: str,
) -> StoryEntry:
    """Update the text of a StoryEntry and record who made the change.

    Args:
        db: Active SQLAlchemy session.
        entry: The ORM instance to update.
        text: New narrative content.
        updated_by: ULID of the User performing the update.

    Returns:
        The updated :class:`~wizards_engine.models.story.StoryEntry` after flush.
    """
    entry.text = text
    entry.updated_by = updated_by
    db.flush()
    db.refresh(entry)
    return entry


def delete_story_entry(
    db: Session,
    entry: StoryEntry,
    *,
    deleted_by: str,
) -> None:
    """Soft-delete a StoryEntry by setting ``is_deleted = True``.

    Args:
        db: Active SQLAlchemy session.
        entry: The ORM instance to soft-delete.
        deleted_by: ULID of the User performing the deletion.
    """
    entry.is_deleted = True
    entry.deleted_by = deleted_by
    db.flush()
