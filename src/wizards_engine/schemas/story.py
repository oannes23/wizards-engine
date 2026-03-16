"""Pydantic schemas for Story API endpoints.

Covers create, update, list-query, and response shapes for the
``/api/v1/stories`` resource including the owners sub-resource.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Enums / Literals
# ---------------------------------------------------------------------------

StoryStatus = Literal["active", "completed", "abandoned"]

VisibilityLevel = Literal[
    "silent", "gm_only", "private", "bonded", "familiar", "public", "global"
]

OwnerType = Literal["character", "group", "location"]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateStoryRequest(BaseModel):
    """Request body for POST /api/v1/stories.

    Attributes
    ----------
    name:
        Required. Story name, 1–200 characters after whitespace stripping.
    summary:
        Optional. Freeform narrative summary.
    status:
        Optional. One of ``active``, ``completed``, ``abandoned``. Defaults to ``active``.
    parent_id:
        Optional. ULID of a parent Story (sub-arc hierarchy).
    tags:
        Optional. Freeform list of tag strings.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    summary: str | None = None
    status: StoryStatus = "active"
    parent_id: str | None = None
    tags: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        return v


class UpdateStoryRequest(BaseModel):
    """Request body for PATCH /api/v1/stories/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  Sending ``null`` for a nullable field clears it.

    Attributes
    ----------
    name:
        New story name.  Must be non-empty if provided.
    summary:
        New summary, or ``null`` to clear.
    status:
        New status.  Any valid enum value may be set freely.
    tags:
        New tags list, or ``null`` to clear.
    visibility_level:
        Override the default visibility for this story.  ``null`` resets to default.
    visibility_overrides:
        List of user IDs explicitly granted visibility.  ``null`` to clear.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    summary: str | None = None
    status: StoryStatus | None = None
    tags: list[str] | None = None
    visibility_level: VisibilityLevel | None = None
    visibility_overrides: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Ensure name is non-empty after stripping if provided."""
        if v is not None and not v:
            raise ValueError("name must not be empty")
        return v


class AddOwnerRequest(BaseModel):
    """Request body for POST /api/v1/stories/{id}/owners.

    Attributes
    ----------
    type:
        Owner type — ``character``, ``group``, or ``location``.
    id:
        ULID of the Game Object to add as owner.
    """

    type: OwnerType
    id: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Ensure owner ID is non-empty."""
        if not v or not v.strip():
            raise ValueError("id must not be empty")
        return v.strip()


class CreateStoryEntryRequest(BaseModel):
    """Request body for POST /api/v1/stories/{id}/entries.

    Attributes
    ----------
    text:
        Required. Narrative content. Must be non-empty after stripping.
    character_id:
        Optional ULID of a Character to associate with this entry.
    game_object_refs:
        Optional list of ``{type, id}`` dicts for additional Game Object references.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str
    character_id: str | None = None
    game_object_refs: list[dict[str, str]] | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Ensure text is non-empty after stripping."""
        if not v:
            raise ValueError("text must not be empty")
        return v


class UpdateStoryEntryRequest(BaseModel):
    """Request body for PATCH /api/v1/stories/{id}/entries/{entry_id}.

    Attributes
    ----------
    text:
        New narrative content. Must be non-empty after stripping.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Ensure text is non-empty after stripping."""
        if not v:
            raise ValueError("text must not be empty")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class StoryOwnerResponse(BaseModel):
    """Response shape for a single story owner record.

    Attributes
    ----------
    type:
        Owner type — ``character``, ``group``, or ``location``.
    id:
        ULID of the owning Game Object.
    """

    model_config = ConfigDict(from_attributes=True)

    type: str
    id: str


class StoryEntryResponse(BaseModel):
    """Response shape for a single narrative entry within a Story.

    Attributes
    ----------
    id:
        ULID primary key.
    story_id:
        ID of the containing Story.
    text:
        Narrative content.
    author_id:
        ID of the User who wrote this entry.
    character_id:
        Optional character linkage.
    session_id:
        Optional session linkage.
    event_id:
        Optional event linkage.
    game_object_refs:
        Optional list of additional Game Object references.
    is_deleted:
        Soft-delete flag.
    updated_by:
        Optional ID of the User who last edited this entry.
    deleted_by:
        Optional ID of the User who soft-deleted this entry.
    created_at:
        ISO 8601 UTC creation timestamp.
    updated_at:
        ISO 8601 UTC last-modified timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    story_id: str
    text: str
    author_id: str
    character_id: str | None
    session_id: str | None
    event_id: str | None
    game_object_refs: list[dict[str, str]] | None
    is_deleted: bool
    updated_by: str | None
    deleted_by: str | None
    created_at: datetime
    updated_at: datetime


class StoryResponse(BaseModel):
    """Response body for a single Story resource.

    Returned by POST (201), GET list items (200), and PATCH (200).
    Does not include ``owners`` or ``entries`` — use ``StoryDetailResponse``
    for the detail endpoint.

    Attributes
    ----------
    id:
        ULID primary key.
    name:
        Story name.
    summary:
        Optional narrative summary.
    status:
        One of ``active``, ``completed``, ``abandoned``.
    parent_id:
        Optional ULID of parent Story.
    tags:
        Optional list of freeform tag strings.
    visibility_level:
        Optional visibility override.
    visibility_overrides:
        Optional list of user IDs explicitly granted access.
    is_deleted:
        Soft-delete flag.
    created_at:
        ISO 8601 UTC creation timestamp.
    updated_at:
        ISO 8601 UTC last-modified timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    summary: str | None
    status: str
    parent_id: str | None
    tags: list[str] | None
    visibility_level: str | None
    visibility_overrides: list[str] | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class StoryDetailResponse(StoryResponse):
    """Detail response for GET /api/v1/stories/{id}.

    Extends ``StoryResponse`` with the owners list and narrative entries.
    Entries are sorted by ``created_at`` ascending; soft-deleted entries
    are excluded.

    Attributes
    ----------
    owners:
        List of owner records (type + id) for this Story.
    entries:
        List of non-deleted narrative entries, oldest first.
    """

    owners: list[StoryOwnerResponse]
    entries: list[StoryEntryResponse]
