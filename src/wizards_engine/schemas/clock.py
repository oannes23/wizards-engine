"""Pydantic schemas for Clock API endpoints.

Covers create, update, list-query, and response shapes for the
``/api/v1/clocks`` and ``/api/v1/groups/{id}/clocks`` resources.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class CreateClockRequest(BaseModel):
    """Request body for POST /api/v1/clocks.

    Attributes
    ----------
    name:
        Required.  Clock name, 1–200 characters after whitespace stripping.
    segments:
        Total segments.  Any positive integer; defaults to 5.
    associated_type:
        Optional.  Type of the associated Game Object: ``"character"``,
        ``"group"``, or ``"location"``.
    associated_id:
        Optional.  ULID of the associated Game Object.  Must be provided
        together with ``associated_type``.
    notes:
        Optional.  Freeform notes.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    segments: int = 5
    associated_type: Literal["character", "group", "location"] | None = None
    associated_id: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("segments")
    @classmethod
    def validate_segments(cls, v: int) -> int:
        """Ensure segments is a positive integer."""
        if v <= 0:
            raise ValueError("segments must be a positive integer (> 0)")
        return v

    @model_validator(mode="after")
    def validate_association_pair(self) -> "CreateClockRequest":
        """Ensure associated_type and associated_id are always provided together."""
        has_type = self.associated_type is not None
        has_id = self.associated_id is not None
        if has_type != has_id:
            raise ValueError(
                "associated_type and associated_id must be provided together"
            )
        return self


class CreateGroupClockRequest(BaseModel):
    """Request body for POST /api/v1/groups/{id}/clocks.

    Sugar route that auto-sets ``associated_type = "group"`` and
    ``associated_id`` to the group ID.  The body must not include
    association fields — those are derived from the URL.

    Attributes
    ----------
    name:
        Required.  Clock name, 1–200 characters after whitespace stripping.
    segments:
        Total segments.  Any positive integer; defaults to 5.
    notes:
        Optional.  Freeform notes.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    segments: int = 5
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("segments")
    @classmethod
    def validate_segments(cls, v: int) -> int:
        """Ensure segments is a positive integer."""
        if v <= 0:
            raise ValueError("segments must be a positive integer (> 0)")
        return v


class UpdateClockRequest(BaseModel):
    """Request body for PATCH /api/v1/clocks/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  Sending ``null`` for a nullable field clears it.

    The following fields are **not** allowed on PATCH and will be rejected
    with 422 if provided (``extra="forbid"``):

    - ``associated_type`` — association is fixed at creation.
    - ``associated_id``   — association is fixed at creation.
    - ``progress``        — progress is changed via GM actions in Phase 4.

    Attributes
    ----------
    name:
        New clock name.  Must be non-empty if provided.
    notes:
        New notes, or ``null`` to clear.
    segments:
        New total segment count.  Must be > 0 if provided.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = None
    notes: str | None = None
    segments: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Ensure name is non-empty after stripping if provided."""
        if v is not None and not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("segments")
    @classmethod
    def validate_segments(cls, v: int | None) -> int | None:
        """Ensure segments is a positive integer if provided."""
        if v is not None and v <= 0:
            raise ValueError("segments must be a positive integer (> 0)")
        return v


class ClockResponse(BaseModel):
    """Response body for a single Clock resource.

    Returned by POST (201), GET detail (200), and PATCH (200).

    Attributes
    ----------
    id:
        ULID primary key.
    name:
        Clock name.
    segments:
        Total segments (positive integer).
    progress:
        Filled segments (0 to segments, soft cap — can exceed segments).
    is_completed:
        Computed field: ``True`` when ``progress >= segments``.  Not stored.
    associated_type:
        Optional type of the associated Game Object.
    associated_id:
        Optional ULID of the associated Game Object.
    notes:
        Optional freeform notes.
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
    segments: int
    progress: int
    is_completed: bool
    associated_type: str | None
    associated_id: str | None
    associated_name: str | None = None
    notes: str | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_model(cls, clock: object) -> "ClockResponse":
        """Build a ClockResponse from a Clock ORM instance.

        Computes ``is_completed`` from ``progress >= segments`` since the
        field is not stored in the database.

        Args:
            clock: A :class:`~wizards_engine.models.clock.Clock` ORM instance.

        Returns:
            A fully populated ``ClockResponse``.
        """
        return cls(
            id=clock.id,  # type: ignore[attr-defined]
            name=clock.name,  # type: ignore[attr-defined]
            segments=clock.segments,  # type: ignore[attr-defined]
            progress=clock.progress,  # type: ignore[attr-defined]
            is_completed=clock.progress >= clock.segments,  # type: ignore[attr-defined]
            associated_type=clock.associated_type,  # type: ignore[attr-defined]
            associated_id=clock.associated_id,  # type: ignore[attr-defined]
            notes=clock.notes,  # type: ignore[attr-defined]
            is_deleted=clock.is_deleted,  # type: ignore[attr-defined]
            created_at=clock.created_at,  # type: ignore[attr-defined]
            updated_at=clock.updated_at,  # type: ignore[attr-defined]
        )
