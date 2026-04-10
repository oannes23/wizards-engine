"""Feed service — query and merge logic for all feed endpoints.

This module implements the feed for Stories 4.4.1 and 4.4.2:
- Querying events where a given Game Object is a target
- Querying story entries for stories owned by the Game Object, and
  story entries where the Game Object appears in ``game_object_refs``
- Merging both sets into a single newest-first chronological stream
- Applying visibility filtering via the existing visibility service
- Excluding ``silent`` events from normal feeds
- ULID cursor pagination
- Filter support matching the Events API

Story 4.4.2 adds:
- ``build_personal_feed``  — all non-silent items visible to the user
- ``build_starred_feed``   — personal feed restricted to starred objects
- ``build_silent_feed``    — GM-only silent events

The feed is a **query pattern** — no new database tables are used.

Story entry visibility uses ``can_user_see_story`` from the visibility
service, applying the full 7-level bond-graph traversal model (including
``bonded``, ``familiar``, ``public``, ``private``, ``gm_only``, ``global``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from wizards_engine.models.event import Event, EventTarget
from wizards_engine.models.starred import StarredObject
from wizards_engine.models.story import Story, StoryEntry, StoryOwner
from wizards_engine.models.user import User
from wizards_engine.schemas.feed import EventFeedItem, FeedResponse, StoryEntryFeedItem
from wizards_engine.services.shared import get_game_object
from wizards_engine.services.visibility import can_user_see_event, can_user_see_story

__all__ = [
    "build_game_object_feed",
    "build_personal_feed",
    "build_starred_feed",
    "build_silent_feed",
]

# ---------------------------------------------------------------------------
# Internal helpers — Event feed items
# ---------------------------------------------------------------------------

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 50


def _build_event_feed_item(
    event: Event,
    current_user: User,
    db: Session,
) -> EventFeedItem:
    """Convert an Event ORM instance to an EventFeedItem schema.

    Args:
        event: The Event ORM instance.  Must have ``targets`` relationship
            loaded.
        current_user: The requesting user, used to compute ``is_own``.
        db: Active SQLAlchemy session, used to resolve target display names.

    Returns:
        A populated :class:`~wizards_engine.schemas.feed.EventFeedItem`.
    """
    targets = []
    for t in event.targets:
        obj = get_game_object(db, t.target_type, t.target_id)
        targets.append({
            "type": t.target_type,
            "id": t.target_id,
            "is_primary": t.is_primary,
            "name": obj.name if obj else None,
        })
    is_own = (
        event.actor_id is not None and event.actor_id == current_user.id
    )
    return EventFeedItem(
        id=event.id,
        type="event",
        timestamp=event.created_at,
        narrative=event.narrative,
        visibility=event.visibility,
        targets=targets,
        is_own=is_own,
        event_type=event.type,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        changes=event.changes,
        created_objects=event.created_objects,
        deleted_objects=event.deleted_objects,
        proposal_id=event.proposal_id,
        parent_event_id=event.parent_event_id,
        session_id=event.session_id,
        metadata=event.metadata_,
    )


# ---------------------------------------------------------------------------
# Internal helpers — Story entry feed items
# ---------------------------------------------------------------------------


def _build_story_entry_feed_item(
    entry: StoryEntry,
    story: Story,
    current_user: User,
) -> StoryEntryFeedItem:
    """Convert a StoryEntry ORM instance to a StoryEntryFeedItem schema.

    Targets for story entries are the union of the Story's owners and
    the entry's ``game_object_refs``, per spec.

    Args:
        entry: The StoryEntry ORM instance.
        story: The parent Story ORM instance.  Must have ``owners``
            relationship loaded.
        current_user: The requesting user, used to compute ``is_own``.

    Returns:
        A populated :class:`~wizards_engine.schemas.feed.StoryEntryFeedItem`.
    """
    # Targets = union of story owners + entry game_object_refs
    owner_targets = [
        {"type": o.owner_type, "id": o.owner_id}
        for o in story.owners
    ]
    ref_targets = (
        [{"type": r["type"], "id": r["id"]} for r in entry.game_object_refs]
        if entry.game_object_refs
        else []
    )

    # Deduplicate while preserving order.
    seen: set[tuple[str, str]] = set()
    targets: list[dict[str, str]] = []
    for t in owner_targets + ref_targets:
        key = (t["type"], t["id"])
        if key not in seen:
            seen.add(key)
            targets.append(t)

    is_own = entry.author_id == current_user.id

    # Visibility: use story's visibility_level, defaulting to "familiar".
    visibility = story.visibility_level or "familiar"

    author_name = entry.author.display_name if entry.author_id else None

    return StoryEntryFeedItem(
        id=entry.id,
        type="story_entry",
        timestamp=entry.created_at,
        narrative=None,
        visibility=visibility,
        targets=targets,
        is_own=is_own,
        story_id=story.id,
        story_name=story.name,
        entry_text=entry.text,
        author_id=entry.author_id,
        author_name=author_name,
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _query_events_for_game_object(
    db: Session,
    object_type: str,
    object_id: str,
    *,
    exclude_silent: bool = True,
    event_type: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[Event]:
    """Return events where *object_type*/*object_id* is a target.

    Args:
        db: Active SQLAlchemy session.
        object_type: The Game Object type (``"character"``, ``"group"``,
            ``"location"``).
        object_id: The ULID of the Game Object.
        exclude_silent: When ``True`` (default), ``silent`` events are
            excluded from the result.
        event_type: Optional event type prefix filter.  Glob-style
            ``character.*`` → SQL ``LIKE 'character.%'``.
        actor_type: Optional actor type filter.
        session_id: Optional session ULID filter.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        target_type: Optional secondary target type filter.
        target_id: Optional secondary target ID filter.

    Returns:
        A list of :class:`~wizards_engine.models.event.Event` instances
        where the Game Object is listed in ``event_targets``.
    """
    q = (
        select(Event)
        .join(
            EventTarget,
            and_(
                EventTarget.event_id == Event.id,
                EventTarget.target_type == object_type,
                EventTarget.target_id == object_id,
            ),
        )
        .distinct()
    )

    if exclude_silent:
        q = q.where(Event.visibility != "silent")

    if event_type is not None:
        if event_type.endswith("*"):
            prefix = event_type[:-1] + "%"
            q = q.where(Event.type.like(prefix))
        else:
            q = q.where(Event.type == event_type)

    if actor_type is not None:
        q = q.where(Event.actor_type == actor_type)

    if session_id is not None:
        q = q.where(Event.session_id == session_id)

    if since is not None:
        q = q.where(Event.created_at >= since)

    if until is not None:
        q = q.where(Event.created_at <= until)

    # Additional target filters (secondary filter on top of the primary join).
    if target_type is not None or target_id is not None:
        secondary_conditions = []
        if target_type is not None:
            secondary_conditions.append(EventTarget.target_type == target_type)
        if target_id is not None:
            secondary_conditions.append(EventTarget.target_id == target_id)

        # Re-join with EventTarget for the secondary filter (different alias).
        from sqlalchemy.orm import aliased
        secondary_et = aliased(EventTarget)
        q = q.join(
            secondary_et,
            and_(secondary_et.event_id == Event.id, *secondary_conditions),
        ).distinct()

    return list(db.scalars(q).all())


def _query_story_entries_for_game_object(
    db: Session,
    object_type: str,
    object_id: str,
    *,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[tuple[StoryEntry, Story]]:
    """Return story entries associated with a Game Object.

    Returns entries from two sources (union):
    1. Entries on stories where the Game Object is an owner
       (via ``story_owners``).
    2. Entries where ``game_object_refs`` contains the Game Object.

    Soft-deleted entries (``is_deleted = True``) and soft-deleted stories
    (``is_deleted = True``) are excluded.

    Args:
        db: Active SQLAlchemy session.
        object_type: The Game Object type.
        object_id: The ULID of the Game Object.
        session_id: Optional session ULID filter.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        target_type: Optional target type filter (applied to the entry's
            ``game_object_refs`` and the story's owner list).
        target_id: Optional target ID filter.

    Returns:
        A list of ``(StoryEntry, Story)`` tuples.
    """
    # Sub-query 1: entries via story ownership.
    q_owned = (
        select(StoryEntry)
        .join(Story, Story.id == StoryEntry.story_id)
        .join(
            StoryOwner,
            and_(
                StoryOwner.story_id == Story.id,
                StoryOwner.owner_type == object_type,
                StoryOwner.owner_id == object_id,
            ),
        )
        .where(StoryEntry.is_deleted.is_(False))
        .where(Story.is_deleted.is_(False))
    )

    if session_id is not None:
        q_owned = q_owned.where(StoryEntry.session_id == session_id)
    if since is not None:
        q_owned = q_owned.where(StoryEntry.created_at >= since)
    if until is not None:
        q_owned = q_owned.where(StoryEntry.created_at <= until)

    entries_from_owned: list[StoryEntry] = list(db.scalars(q_owned).all())

    # Sub-query 2: entries where game_object_refs references this object.
    # SQLite JSON: we rely on the JSON column containing ``[..., {"type": ..., "id": ...}, ...]``.
    # We use a Python-side filter since SQLite's JSON support via SQLAlchemy
    # requires care; for our small data scale this is fine.
    q_refs = (
        select(StoryEntry)
        .join(Story, Story.id == StoryEntry.story_id)
        .where(StoryEntry.is_deleted.is_(False))
        .where(Story.is_deleted.is_(False))
        .where(StoryEntry.game_object_refs.is_not(None))
    )

    if session_id is not None:
        q_refs = q_refs.where(StoryEntry.session_id == session_id)
    if since is not None:
        q_refs = q_refs.where(StoryEntry.created_at >= since)
    if until is not None:
        q_refs = q_refs.where(StoryEntry.created_at <= until)

    entries_from_refs_raw: list[StoryEntry] = list(db.scalars(q_refs).all())

    # Python-side filter for game_object_refs match.
    entries_from_refs = [
        e for e in entries_from_refs_raw
        if e.game_object_refs
        and any(
            r.get("type") == object_type and r.get("id") == object_id
            for r in e.game_object_refs
        )
    ]

    # Merge, deduplicate by entry ID, and load parent stories.
    seen_entry_ids: set[str] = set()
    result: list[tuple[StoryEntry, Story]] = []

    for entry in entries_from_owned + entries_from_refs:
        if entry.id in seen_entry_ids:
            continue
        seen_entry_ids.add(entry.id)
        story = db.get(Story, entry.story_id)
        if story is None or story.is_deleted:
            continue

        # Apply secondary target filters (target_type / target_id on owners).
        if target_type is not None or target_id is not None:
            owner_ids = {(o.owner_type, o.owner_id) for o in story.owners}
            refs = entry.game_object_refs or []
            ref_ids = {(r.get("type"), r.get("id")) for r in refs}
            all_targets = owner_ids | ref_ids

            match = True
            if target_type is not None and not any(
                t[0] == target_type for t in all_targets
            ):
                match = False
            if target_id is not None and not any(
                t[1] == target_id for t in all_targets
            ):
                match = False
            if not match:
                continue

        result.append((entry, story))

    return result


# ---------------------------------------------------------------------------
# Public API — build_game_object_feed
# ---------------------------------------------------------------------------


def build_game_object_feed(
    db: Session,
    current_user: User,
    object_type: str,
    object_id: str,
    *,
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    event_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> FeedResponse:
    """Build a merged, visibility-filtered feed for a single Game Object.

    Queries both events and story entries referencing the specified Game
    Object, merges them into a single newest-first list, applies
    visibility filtering, and paginates with ULID cursor semantics.

    Event-only filters (``event_type``, ``actor_type``) exclude all
    ``story_entry`` items from the result when used.

    Args:
        db: Active SQLAlchemy session.
        current_user: The requesting user (Player or GM).
        object_type: Game Object type — ``"character"``, ``"group"``,
            or ``"location"``.
        object_id: ULID of the Game Object.
        after: ULID cursor for pagination.  Return items with IDs
            *less than* this value (older, newest-first ordering).
        limit: Page size (default 50, max 100).
        event_type: Optional event type prefix filter (e.g.
            ``"character.*"``).  Applies only to events; also excludes
            story entries from the result.
        target_type: Optional filter by target Game Object type.
        target_id: Optional filter by specific target ULID.
        actor_type: Optional filter by actor type.  Applies only to
            events; also excludes story entries from the result.
        session_id: Optional filter by session ULID.
        since: Optional lower bound on timestamp (inclusive).
        until: Optional upper bound on timestamp (inclusive).

    Returns:
        A :class:`~wizards_engine.schemas.feed.FeedResponse` with the
        merged, visibility-filtered, paginated feed items.
    """
    limit = min(limit, _MAX_LIMIT)

    # When event-only filters are active, we exclude story entries entirely.
    event_only_filters_active = event_type is not None or actor_type is not None

    # ------------------------------------------------------------------
    # 1. Collect events targeting this Game Object.
    # ------------------------------------------------------------------
    raw_events = _query_events_for_game_object(
        db,
        object_type,
        object_id,
        exclude_silent=True,
        event_type=event_type,
        actor_type=actor_type,
        session_id=session_id,
        since=since,
        until=until,
        target_type=target_type,
        target_id=target_id,
    )

    # Visibility filter events.
    visible_events = [
        e for e in raw_events
        if can_user_see_event(db, current_user, e)
    ]

    # Convert to feed items.
    event_items: list[EventFeedItem] = [
        _build_event_feed_item(e, current_user, db) for e in visible_events
    ]

    # ------------------------------------------------------------------
    # 2. Collect story entries (skipped when event-only filters active).
    # ------------------------------------------------------------------
    entry_items: list[StoryEntryFeedItem] = []

    if not event_only_filters_active:
        raw_entries = _query_story_entries_for_game_object(
            db,
            object_type,
            object_id,
            session_id=session_id,
            since=since,
            until=until,
            target_type=target_type,
            target_id=target_id,
        )

        for entry, story in raw_entries:
            if not can_user_see_story(db, current_user, story):
                continue
            entry_items.append(
                _build_story_entry_feed_item(entry, story, current_user)
            )

    # ------------------------------------------------------------------
    # 3. Merge and sort newest-first by ID (ULID = time-sortable).
    # ------------------------------------------------------------------
    all_items: list[EventFeedItem | StoryEntryFeedItem] = event_items + entry_items
    all_items.sort(key=lambda x: x.id, reverse=True)

    # ------------------------------------------------------------------
    # 4. Apply ULID cursor pagination.
    # ------------------------------------------------------------------
    if after is not None:
        all_items = [item for item in all_items if item.id < after]

    has_more = len(all_items) > limit
    page_items = all_items[:limit]
    next_cursor = page_items[-1].id if has_more and page_items else None

    return FeedResponse(
        items=page_items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# Internal helpers — global / personal event queries (Story 4.4.2)
# ---------------------------------------------------------------------------


def _query_all_events(
    db: Session,
    *,
    exclude_silent: bool = True,
    silent_only: bool = False,
    event_type: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[Event]:
    """Return events across all Game Objects, with optional filters.

    Used by the personal feed and the silent feed.

    Args:
        db: Active SQLAlchemy session.
        exclude_silent: When ``True`` (default), ``silent`` events are
            excluded.  Mutually exclusive with ``silent_only``.
        silent_only: When ``True``, *only* ``silent`` events are returned.
            Takes precedence over ``exclude_silent``.
        event_type: Optional event type prefix filter.
        actor_type: Optional actor type filter.
        session_id: Optional session ULID filter.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        target_type: Optional target type filter.
        target_id: Optional target ID filter.

    Returns:
        A list of :class:`~wizards_engine.models.event.Event` instances.
    """
    q = select(Event)

    if silent_only:
        q = q.where(Event.visibility == "silent")
    elif exclude_silent:
        q = q.where(Event.visibility != "silent")

    if event_type is not None:
        if event_type.endswith("*"):
            prefix = event_type[:-1] + "%"
            q = q.where(Event.type.like(prefix))
        else:
            q = q.where(Event.type == event_type)

    if actor_type is not None:
        q = q.where(Event.actor_type == actor_type)

    if session_id is not None:
        q = q.where(Event.session_id == session_id)

    if since is not None:
        q = q.where(Event.created_at >= since)

    if until is not None:
        q = q.where(Event.created_at <= until)

    if target_type is not None or target_id is not None:
        conditions = []
        if target_type is not None:
            conditions.append(EventTarget.target_type == target_type)
        if target_id is not None:
            conditions.append(EventTarget.target_id == target_id)
        q = (
            q.join(EventTarget, and_(EventTarget.event_id == Event.id, *conditions))
            .distinct()
        )

    return list(db.scalars(q).all())


def _query_all_story_entries(
    db: Session,
    *,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[tuple[StoryEntry, Story]]:
    """Return all non-deleted story entries with their parent stories.

    Used by the personal feed.

    Args:
        db: Active SQLAlchemy session.
        session_id: Optional session ULID filter.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        target_type: Optional target type filter.
        target_id: Optional target ID filter.

    Returns:
        A list of ``(StoryEntry, Story)`` tuples.
    """
    q = (
        select(StoryEntry)
        .join(Story, Story.id == StoryEntry.story_id)
        .where(StoryEntry.is_deleted.is_(False))
        .where(Story.is_deleted.is_(False))
    )

    if session_id is not None:
        q = q.where(StoryEntry.session_id == session_id)
    if since is not None:
        q = q.where(StoryEntry.created_at >= since)
    if until is not None:
        q = q.where(StoryEntry.created_at <= until)

    entries: list[StoryEntry] = list(db.scalars(q).all())

    result: list[tuple[StoryEntry, Story]] = []
    for entry in entries:
        story = db.get(Story, entry.story_id)
        if story is None or story.is_deleted:
            continue

        # Apply target filters (target_type / target_id) against the
        # union of story owners + entry refs.
        if target_type is not None or target_id is not None:
            owner_pairs = {(o.owner_type, o.owner_id) for o in story.owners}
            ref_pairs = {
                (r.get("type"), r.get("id"))
                for r in (entry.game_object_refs or [])
            }
            all_targets = owner_pairs | ref_pairs

            if target_type is not None and not any(
                t[0] == target_type for t in all_targets
            ):
                continue
            if target_id is not None and not any(
                t[1] == target_id for t in all_targets
            ):
                continue

        result.append((entry, story))

    return result


def _query_story_entries_for_starred(
    db: Session,
    starred: list[StarredObject],
    *,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[tuple[StoryEntry, Story]]:
    """Return story entries scoped to a list of starred Game Objects.

    Returns entries where:
    1. The parent Story is owned by any starred object (via ``story_owners``),
       OR
    2. The entry's ``game_object_refs`` references any starred object.

    Deduplicates by entry ID.

    Args:
        db: Active SQLAlchemy session.
        starred: List of :class:`~wizards_engine.models.starred.StarredObject`
            rows belonging to the current user.
        session_id: Optional session ULID filter.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        target_type: Optional target type filter.
        target_id: Optional target ID filter.

    Returns:
        A list of ``(StoryEntry, Story)`` tuples.
    """
    if not starred:
        return []

    # Build the set of (type, id) pairs for starred objects.
    starred_pairs: set[tuple[str, str]] = {
        (s.object_type, s.object_id) for s in starred
    }

    # Query all non-deleted entries.
    q = (
        select(StoryEntry)
        .join(Story, Story.id == StoryEntry.story_id)
        .where(StoryEntry.is_deleted.is_(False))
        .where(Story.is_deleted.is_(False))
    )

    if session_id is not None:
        q = q.where(StoryEntry.session_id == session_id)
    if since is not None:
        q = q.where(StoryEntry.created_at >= since)
    if until is not None:
        q = q.where(StoryEntry.created_at <= until)

    entries: list[StoryEntry] = list(db.scalars(q).all())

    seen_ids: set[str] = set()
    result: list[tuple[StoryEntry, Story]] = []

    for entry in entries:
        if entry.id in seen_ids:
            continue

        story = db.get(Story, entry.story_id)
        if story is None or story.is_deleted:
            continue

        # Check if any story owner or entry ref matches a starred object.
        owner_pairs = {(o.owner_type, o.owner_id) for o in story.owners}
        ref_pairs = {
            (r.get("type"), r.get("id"))
            for r in (entry.game_object_refs or [])
        }
        all_pairs = owner_pairs | ref_pairs

        if not (all_pairs & starred_pairs):
            continue

        # Apply secondary target filters.
        if target_type is not None or target_id is not None:
            if target_type is not None and not any(
                t[0] == target_type for t in all_pairs
            ):
                continue
            if target_id is not None and not any(
                t[1] == target_id for t in all_pairs
            ):
                continue

        seen_ids.add(entry.id)
        result.append((entry, story))

    return result


def _query_events_for_starred(
    db: Session,
    starred: list[StarredObject],
    *,
    event_type: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[Event]:
    """Return non-silent events where any target matches a starred object.

    Args:
        db: Active SQLAlchemy session.
        starred: List of :class:`~wizards_engine.models.starred.StarredObject`
            rows belonging to the current user.
        event_type: Optional event type prefix filter.
        actor_type: Optional actor type filter.
        session_id: Optional session ULID filter.
        since: Optional lower bound on ``created_at`` (inclusive).
        until: Optional upper bound on ``created_at`` (inclusive).
        target_type: Optional target type filter.
        target_id: Optional target ID filter.

    Returns:
        A list of :class:`~wizards_engine.models.event.Event` instances.
    """
    if not starred:
        return []

    starred_pairs: set[tuple[str, str]] = {
        (s.object_type, s.object_id) for s in starred
    }

    # Build OR conditions: event must have at least one target matching any
    # starred pair.
    or_conditions = [
        and_(
            EventTarget.target_type == obj_type,
            EventTarget.target_id == obj_id,
        )
        for obj_type, obj_id in starred_pairs
    ]

    q = (
        select(Event)
        .join(
            EventTarget,
            and_(
                EventTarget.event_id == Event.id,
                or_(*or_conditions),
            ),
        )
        .where(Event.visibility != "silent")
        .distinct()
    )

    if event_type is not None:
        if event_type.endswith("*"):
            prefix = event_type[:-1] + "%"
            q = q.where(Event.type.like(prefix))
        else:
            q = q.where(Event.type == event_type)

    if actor_type is not None:
        q = q.where(Event.actor_type == actor_type)

    if session_id is not None:
        q = q.where(Event.session_id == session_id)

    if since is not None:
        q = q.where(Event.created_at >= since)

    if until is not None:
        q = q.where(Event.created_at <= until)

    # Secondary target filter: if specified, also require this target.
    if target_type is not None or target_id is not None:
        from sqlalchemy.orm import aliased
        secondary_et = aliased(EventTarget)
        secondary_conditions = []
        if target_type is not None:
            secondary_conditions.append(secondary_et.target_type == target_type)
        if target_id is not None:
            secondary_conditions.append(secondary_et.target_id == target_id)
        q = q.join(
            secondary_et,
            and_(secondary_et.event_id == Event.id, *secondary_conditions),
        ).distinct()

    return list(db.scalars(q).all())


# ---------------------------------------------------------------------------
# Shared merge / paginate helper
# ---------------------------------------------------------------------------


def _merge_and_paginate(
    event_items: list[EventFeedItem],
    entry_items: list[StoryEntryFeedItem],
    *,
    after: str | None,
    limit: int,
) -> FeedResponse:
    """Merge event and story entry items, sort newest-first, and paginate.

    Args:
        event_items: Converted and visibility-filtered event feed items.
        entry_items: Converted and visibility-filtered story entry feed items.
        after: ULID cursor — return items with IDs *less than* this value.
        limit: Maximum number of items to return per page.

    Returns:
        A :class:`~wizards_engine.schemas.feed.FeedResponse`.
    """
    all_items: list[EventFeedItem | StoryEntryFeedItem] = event_items + entry_items
    all_items.sort(key=lambda x: x.id, reverse=True)

    if after is not None:
        all_items = [item for item in all_items if item.id < after]

    has_more = len(all_items) > limit
    page_items = all_items[:limit]
    next_cursor = page_items[-1].id if has_more and page_items else None

    return FeedResponse(
        items=page_items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# Public API — build_personal_feed (Story 4.4.2)
# ---------------------------------------------------------------------------


def build_personal_feed(
    db: Session,
    current_user: User,
    *,
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    event_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> FeedResponse:
    """Build the complete personal feed for *current_user*.

    For players: all non-silent events visible to them (via visibility
    filtering) plus all story entries visible to them.  For the GM: all
    non-silent events and all story entries.

    Event-only filters (``event_type``, ``actor_type``) exclude all
    ``story_entry`` items from the result when used.

    Args:
        db: Active SQLAlchemy session.
        current_user: The requesting user (Player or GM).
        after: ULID cursor for pagination.
        limit: Page size (default 50, max 100).
        event_type: Optional event type prefix filter.
        target_type: Optional filter by target Game Object type.
        target_id: Optional filter by specific target ULID.
        actor_type: Optional filter by actor type.
        session_id: Optional filter by session ULID.
        since: Optional lower bound on timestamp (inclusive).
        until: Optional upper bound on timestamp (inclusive).

    Returns:
        A :class:`~wizards_engine.schemas.feed.FeedResponse`.
    """
    limit = min(limit, _MAX_LIMIT)
    event_only_filters_active = event_type is not None or actor_type is not None

    # ------------------------------------------------------------------
    # 1. Collect all non-silent events and apply visibility filter.
    # ------------------------------------------------------------------
    raw_events = _query_all_events(
        db,
        exclude_silent=True,
        event_type=event_type,
        actor_type=actor_type,
        session_id=session_id,
        since=since,
        until=until,
        target_type=target_type,
        target_id=target_id,
    )

    visible_events = [
        e for e in raw_events if can_user_see_event(db, current_user, e)
    ]

    event_items: list[EventFeedItem] = [
        _build_event_feed_item(e, current_user, db) for e in visible_events
    ]

    # ------------------------------------------------------------------
    # 2. Collect story entries (skipped when event-only filters active).
    # ------------------------------------------------------------------
    entry_items: list[StoryEntryFeedItem] = []

    if not event_only_filters_active:
        raw_entries = _query_all_story_entries(
            db,
            session_id=session_id,
            since=since,
            until=until,
            target_type=target_type,
            target_id=target_id,
        )
        for entry, story in raw_entries:
            if not can_user_see_story(db, current_user, story):
                continue
            entry_items.append(
                _build_story_entry_feed_item(entry, story, current_user)
            )

    # ------------------------------------------------------------------
    # 3. Merge, sort, paginate.
    # ------------------------------------------------------------------
    return _merge_and_paginate(event_items, entry_items, after=after, limit=limit)


# ---------------------------------------------------------------------------
# Public API — build_starred_feed (Story 4.4.2)
# ---------------------------------------------------------------------------


def build_starred_feed(
    db: Session,
    current_user: User,
    *,
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    event_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> FeedResponse:
    """Build the starred feed for *current_user*.

    Same as the personal feed but restricted to Game Objects the user has
    starred.  Uses the ``starred_objects`` table to determine which objects
    are starred.

    Event-only filters (``event_type``, ``actor_type``) exclude all
    ``story_entry`` items from the result when used.

    Args:
        db: Active SQLAlchemy session.
        current_user: The requesting user (Player or GM).
        after: ULID cursor for pagination.
        limit: Page size (default 50, max 100).
        event_type: Optional event type prefix filter.
        target_type: Optional filter by target Game Object type.
        target_id: Optional filter by specific target ULID.
        actor_type: Optional filter by actor type.
        session_id: Optional filter by session ULID.
        since: Optional lower bound on timestamp (inclusive).
        until: Optional upper bound on timestamp (inclusive).

    Returns:
        A :class:`~wizards_engine.schemas.feed.FeedResponse`.
    """
    limit = min(limit, _MAX_LIMIT)
    event_only_filters_active = event_type is not None or actor_type is not None

    # Load the user's starred objects.
    starred: list[StarredObject] = list(
        db.scalars(
            select(StarredObject).where(StarredObject.user_id == current_user.id)
        ).all()
    )

    if not starred:
        return FeedResponse(items=[], next_cursor=None, has_more=False)

    # ------------------------------------------------------------------
    # 1. Events targeting any starred object.
    # ------------------------------------------------------------------
    raw_events = _query_events_for_starred(
        db,
        starred,
        event_type=event_type,
        actor_type=actor_type,
        session_id=session_id,
        since=since,
        until=until,
        target_type=target_type,
        target_id=target_id,
    )

    visible_events = [
        e for e in raw_events if can_user_see_event(db, current_user, e)
    ]

    event_items: list[EventFeedItem] = [
        _build_event_feed_item(e, current_user, db) for e in visible_events
    ]

    # ------------------------------------------------------------------
    # 2. Story entries for starred objects.
    # ------------------------------------------------------------------
    entry_items: list[StoryEntryFeedItem] = []

    if not event_only_filters_active:
        raw_entries = _query_story_entries_for_starred(
            db,
            starred,
            session_id=session_id,
            since=since,
            until=until,
            target_type=target_type,
            target_id=target_id,
        )
        for entry, story in raw_entries:
            if not can_user_see_story(db, current_user, story):
                continue
            entry_items.append(
                _build_story_entry_feed_item(entry, story, current_user)
            )

    # ------------------------------------------------------------------
    # 3. Merge, sort, paginate.
    # ------------------------------------------------------------------
    return _merge_and_paginate(event_items, entry_items, after=after, limit=limit)


# ---------------------------------------------------------------------------
# Public API — build_silent_feed (Story 4.4.2)
# ---------------------------------------------------------------------------


def build_silent_feed(
    db: Session,
    current_user: User,
    *,
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    event_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_type: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> FeedResponse:
    """Build the GM-only silent event feed.

    Returns only ``silent``-visibility events.  Story entries are excluded
    (they don't have a ``silent`` visibility level).  The caller is
    responsible for enforcing that ``current_user`` is the GM before calling
    this function.

    Event-only filters (``event_type``, ``actor_type``) are accepted for
    API consistency but only affect the event query (no story entries to
    exclude here).

    Args:
        db: Active SQLAlchemy session.
        current_user: The requesting user (must be GM — enforced by caller).
        after: ULID cursor for pagination.
        limit: Page size (default 50, max 100).
        event_type: Optional event type prefix filter.
        target_type: Optional filter by target Game Object type.
        target_id: Optional filter by specific target ULID.
        actor_type: Optional filter by actor type.
        session_id: Optional filter by session ULID.
        since: Optional lower bound on timestamp (inclusive).
        until: Optional upper bound on timestamp (inclusive).

    Returns:
        A :class:`~wizards_engine.schemas.feed.FeedResponse`.
    """
    limit = min(limit, _MAX_LIMIT)

    raw_events = _query_all_events(
        db,
        exclude_silent=False,
        silent_only=True,
        event_type=event_type,
        actor_type=actor_type,
        session_id=session_id,
        since=since,
        until=until,
        target_type=target_type,
        target_id=target_id,
    )

    event_items: list[EventFeedItem] = [
        _build_event_feed_item(e, current_user, db) for e in raw_events
    ]

    return _merge_and_paginate(event_items, [], after=after, limit=limit)
