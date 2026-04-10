"""Pydantic schemas for Feed API endpoints.

Covers the discriminated union feed item response shapes and the feed
response envelope for all per-Game Object feed endpoints.

Feed items are one of two concrete types:
- ``EventFeedItem``      — an event from the event log
- ``StoryEntryFeedItem`` — an entry from a story

Both share a common base (``FeedItemBase``) with ``id``, ``type``,
``timestamp``, ``narrative``, ``visibility``, ``targets``, and ``is_own``.
The ``type`` literal field drives the Pydantic discriminated union.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


class FeedItemBase(BaseModel):
    """Fields shared by all feed item types.

    Attributes
    ----------
    id:
        ULID primary key of the underlying Event or StoryEntry.
    type:
        Discriminator: ``"event"`` or ``"story_entry"``.
    timestamp:
        ISO 8601 UTC timestamp when the item was created.
    narrative:
        Optional human-readable narrative text.
    visibility:
        The item's visibility level (one of the 7 canonical levels).
    targets:
        List of ``{type, id}`` dicts for Game Objects associated with
        this item.
    is_own:
        ``True`` when the authenticated player is the actor (event) or
        author (story entry) of this item.
    """

    id: str
    type: str
    timestamp: datetime
    narrative: str | None
    visibility: str
    targets: list[dict[str, Any]]
    is_own: bool


# ---------------------------------------------------------------------------
# Event feed item
# ---------------------------------------------------------------------------


class EventFeedItem(FeedItemBase):
    """A feed item representing a single event from the event log.

    Attributes
    ----------
    type:
        Always ``"event"`` — the discriminator literal.
    event_type:
        Convention-based ``{domain}.{action}`` string (e.g.
        ``character.stress_changed``).
    actor_type:
        One of ``"player"``, ``"gm"``, or ``"system"``.
    actor_id:
        ULID of the acting user, or ``None`` for system-generated events.
    changes:
        Mapping of change keys to change dicts.
    created_objects:
        List of ``{type, id}`` dicts for objects created by this event,
        or ``None``.
    deleted_objects:
        List of ``{type, id}`` dicts for objects soft-deleted by this
        event, or ``None``.
    proposal_id:
        ULID of the related Proposal, or ``None``.
    parent_event_id:
        ULID of the parent Event (rider events only), or ``None``.
    session_id:
        ULID of the Session this event belongs to, or ``None``.
    metadata:
        Optional freeform JSON stored in the event's ``metadata_`` column.
    """

    type: Literal["event"] = "event"
    event_type: str
    actor_type: str
    actor_id: str | None
    changes: dict[str, Any]
    created_objects: list[dict[str, Any]] | None
    deleted_objects: list[dict[str, Any]] | None
    proposal_id: str | None
    parent_event_id: str | None
    session_id: str | None
    metadata: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Story entry feed item
# ---------------------------------------------------------------------------


class StoryEntryFeedItem(FeedItemBase):
    """A feed item representing a single entry from a story.

    Attributes
    ----------
    type:
        Always ``"story_entry"`` — the discriminator literal.
    story_id:
        ULID of the parent Story.
    story_name:
        Display name of the parent Story.
    entry_text:
        The body text of the story entry.
    author_id:
        ULID of the User who wrote the entry.
    """

    type: Literal["story_entry"] = "story_entry"
    story_id: str
    story_name: str
    entry_text: str
    author_id: str | None
    author_name: str | None = None


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

FeedItem = Annotated[
    EventFeedItem | StoryEntryFeedItem,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Paginated feed response
# ---------------------------------------------------------------------------


class FeedResponse(BaseModel):
    """Paginated feed response envelope.

    Attributes
    ----------
    items:
        The current page of feed items (mixed ``EventFeedItem`` and
        ``StoryEntryFeedItem`` instances, sorted newest-first).
    next_cursor:
        The ULID of the last item in the page.  Pass as ``?after=`` for
        the next page.  ``None`` when no more items exist.
    has_more:
        ``True`` when additional pages exist beyond this one.
    """

    items: list[EventFeedItem | StoryEntryFeedItem]
    next_cursor: str | None
    has_more: bool
