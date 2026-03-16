"""Pydantic schemas for Group API endpoints.

Covers create, update, list-query, and response shapes for the
``/api/v1/groups`` resource.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from wizards_engine.schemas.bond import BondGroups, GroupMemberResponse, TraitDisplayResponse


class CreateGroupRequest(BaseModel):
    """Request body for POST /api/v1/groups.

    Attributes
    ----------
    name:
        Required. Group name, 1–200 characters after whitespace stripping.
    description:
        Optional. Freeform background or concept text.
    tier:
        Required. Non-negative integer representing power/influence level.
    notes:
        Optional. Freeform GM notes.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str | None = None
    tier: int
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: int) -> int:
        """Ensure tier is a non-negative integer."""
        if v < 0:
            raise ValueError("tier must be a non-negative integer")
        return v


class UpdateGroupRequest(BaseModel):
    """Request body for PATCH /api/v1/groups/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  Sending ``null`` for a nullable field clears it.

    ``tier`` is intentionally excluded — tier changes come via GM actions
    in Phase 4.

    Attributes
    ----------
    name:
        New group name.  Must be non-empty if provided.
    description:
        New description, or ``null`` to clear.
    notes:
        New notes, or ``null`` to clear.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    description: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Ensure name is non-empty after stripping if provided."""
        if v is not None and not v:
            raise ValueError("name must not be empty")
        return v


class GroupResponse(BaseModel):
    """Response body for a single Group resource.

    Returned by POST (201), GET detail (200), and PATCH (200).

    Attributes
    ----------
    id:
        ULID primary key.
    name:
        Group name.
    description:
        Optional background/concept text.
    tier:
        Power/influence level. Non-negative integer.
    notes:
        Optional GM notes.
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
    description: str | None
    tier: int
    notes: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class GroupDetailResponse(GroupResponse):
    """Extended response for GET /api/v1/groups/{id}.

    Adds traits, bonds, and computed members list.

    Attributes
    ----------
    traits:
        Descriptive trait slots on this group (``slot_type = "group_trait"``).
        Active traits only.
    bonds:
        All bonds on this group — both outbound and inbound bidirectional —
        grouped by active/past status.  Labels are normalized to the group's
        perspective.
    members:
        Computed list of Characters with an active bond targeting this group.
        Derived from the bond graph; not stored separately.
    """

    traits: list[TraitDisplayResponse] = []
    bonds: BondGroups = BondGroups()
    members: list[GroupMemberResponse] = []
