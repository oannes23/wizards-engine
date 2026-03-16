"""Pydantic schemas for Trait Template API endpoints.

Covers create, update, and response shapes for the
``/api/v1/trait-templates`` resource.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class CreateTraitTemplateRequest(BaseModel):
    """Request body for POST /api/v1/trait-templates.

    Attributes
    ----------
    name:
        Required.  Template name, 1–200 characters after whitespace stripping.
    description:
        Required.  Freeform description of the trait.
    type:
        Required.  Either ``"core"`` or ``"role"``.  Immutable after creation.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str
    type: Literal["core", "role"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is non-empty after stripping."""
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 200:
            raise ValueError("name must be 200 characters or fewer")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Ensure description is non-empty after stripping."""
        if not v:
            raise ValueError("description must not be empty")
        return v


class UpdateTraitTemplateRequest(BaseModel):
    """Request body for PATCH /api/v1/trait-templates/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  The ``type`` field is intentionally excluded — type is
    immutable after creation and cannot be changed.  Sending ``type`` in
    the body raises a 422 validation error.

    Attributes
    ----------
    name:
        New template name.  Must be non-empty if provided.
    description:
        New description.  Must be non-empty if provided.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_type_field(cls, values: Any) -> Any:
        """Reject any attempt to include ``type`` in an update request.

        ``type`` is immutable after creation — sending it in a PATCH body
        is an error, not a silently-ignored field.
        """
        if isinstance(values, dict) and "type" in values:
            raise ValueError(
                "type is immutable and cannot be changed after creation"
            )
        return values

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Ensure name is non-empty after stripping if provided."""
        if v is not None and not v:
            raise ValueError("name must not be empty")
        if v is not None and len(v) > 200:
            raise ValueError("name must be 200 characters or fewer")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Ensure description is non-empty after stripping if provided."""
        if v is not None and not v:
            raise ValueError("description must not be empty")
        return v


class TraitTemplateResponse(BaseModel):
    """Response body for a single Trait Template resource.

    Returned by POST (201), GET detail (200), and PATCH (200).

    Attributes
    ----------
    id:
        ULID primary key.
    name:
        Template name.
    description:
        Freeform trait description.
    type:
        Template type — ``"core"`` or ``"role"``.  Immutable after creation.
    is_deleted:
        Soft-delete flag.  Soft-deleted templates are hidden from the list
        endpoint but remain resolvable by ID for instance display.
    created_at:
        ISO 8601 UTC creation timestamp.
    updated_at:
        ISO 8601 UTC last-modified timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    type: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
