"""Pydantic schemas for Location API endpoints.

Covers create, update, list-query, and response shapes for the
``/api/v1/locations`` resource.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from wizards_engine.schemas.bond import BondGroups, TraitDisplayResponse
from wizards_engine.schemas.character import EntityRef


class PresenceTiers(BaseModel):
    """Bond-distance presence tiers for a Location.

    Attributes
    ----------
    common:
        Characters directly bonded to this Location (1-hop).
    familiar:
        Characters reachable through one Character intermediary (2-hop).
    known:
        Characters reachable through two intermediaries (3-hop).
    """

    common: list[EntityRef] = []
    familiar: list[EntityRef] = []
    known: list[EntityRef] = []


class CreateLocationRequest(BaseModel):
    """Request body for POST /api/v1/locations.

    Attributes
    ----------
    name:
        Required. Location name, 1–200 characters after whitespace stripping.
    description:
        Optional. Freeform description of the location.
    parent_id:
        Optional. ULID of the parent location. Must reference an existing
        location. Establishes the hierarchy. Not updatable via PATCH.
    notes:
        Optional. Freeform GM notes.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str | None = None
    parent_id: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        return v


class UpdateLocationRequest(BaseModel):
    """Request body for PATCH /api/v1/locations/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  Sending ``null`` for a nullable field clears it.

    ``parent_id`` is intentionally excluded — hierarchy changes come via
    GM actions in Phase 4.

    Attributes
    ----------
    name:
        New location name.  Must be non-empty if provided.
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


class LocationResponse(BaseModel):
    """Response body for a single Location resource.

    Returned by POST (201), PATCH (200), and list endpoints (200).

    Attributes
    ----------
    id:
        ULID primary key.
    name:
        Location name.
    description:
        Optional description text.
    parent_id:
        Optional ULID of the parent location in the hierarchy.
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
    parent_id: str | None
    notes: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class LocationDetailResponse(LocationResponse):
    """Extended response for GET /api/v1/locations/{id}.

    Adds feature traits, bonds, and bond-distance presence tiers.

    Attributes
    ----------
    traits:
        Feature trait slots on this location (``slot_type = "feature_trait"``).
        Active traits only.
    bonds:
        All bonds on this location — both outbound and inbound bidirectional —
        grouped by active/past status.  Labels are normalized to the location's
        perspective.
    presence:
        Bond-distance character tiers: ``common`` (1-hop), ``familiar``
        (2-hop), and ``known`` (3-hop).  Computed on read from the bond graph
        using the Character-intermediary traversal algorithm.
    """

    traits: list[TraitDisplayResponse] = []
    bonds: BondGroups = BondGroups()
    presence: PresenceTiers = PresenceTiers()

    # Bond-distance from the requesting user's character to this entity.
    # None for GMs, Viewers, and users without a linked character.
    bond_distance: int | None = None
