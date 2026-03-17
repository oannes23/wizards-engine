"""Pydantic schemas for Event API endpoints.

Covers response shapes and the PATCH visibility request body for
``/api/v1/events``.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from wizards_engine.services.event import VALID_VISIBILITY_LEVELS


class EventTargetResponse(BaseModel):
    """A single target Game Object associated with an Event.

    Attributes
    ----------
    target_type:
        Type of the target — e.g. ``"character"``, ``"group"``,
        ``"location"``.
    target_id:
        ULID of the target object.
    is_primary:
        ``True`` for the primary target; ``False`` for secondary targets.
    """

    model_config = ConfigDict(from_attributes=True)

    target_type: str
    target_id: str
    is_primary: bool


class EventResponse(BaseModel):
    """Response body for a single Event resource.

    Returned by GET /events, GET /events/{id}, and PATCH /events/{id}/visibility.

    Attributes
    ----------
    id:
        ULID primary key.
    type:
        Convention-based ``{domain}.{action}`` string (e.g. ``character.stress_changed``).
    actor_type:
        One of ``"player"``, ``"gm"``, or ``"system"``.
    actor_id:
        ULID of the acting user, or ``None`` for system-generated events.
    changes:
        Mapping of change keys to change dicts.  Always present (empty dict
        if no changes recorded).
    created_objects:
        List of ``{type, id}`` dicts for objects created by this event, or
        ``None`` if no objects were created.
    deleted_objects:
        List of ``{type, id}`` dicts for objects soft-deleted by this event,
        or ``None`` if no objects were deleted.
    narrative:
        Optional human-readable description of the event.
    visibility:
        One of the 7 canonical visibility levels: ``silent``, ``gm_only``,
        ``private``, ``bonded``, ``familiar``, ``public``, ``global``.
    proposal_id:
        ULID of the related Proposal, or ``None``.
    parent_event_id:
        ULID of the parent Event (rider events only), or ``None``.
    session_id:
        ULID of the Session this event belongs to, or ``None``.
    metadata:
        Optional freeform JSON stored in the event's ``metadata_`` column.
        Exposed as ``metadata`` in the API response.
    created_at:
        ISO 8601 UTC creation timestamp.
    targets:
        List of associated :class:`EventTargetResponse` objects.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    actor_type: str
    actor_id: str | None
    changes: dict[str, Any]
    created_objects: list[dict[str, Any]] | None
    deleted_objects: list[dict[str, Any]] | None
    narrative: str | None
    visibility: str
    proposal_id: str | None
    parent_event_id: str | None
    session_id: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
    targets: list[EventTargetResponse]

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Override to remap ``metadata_`` ORM attribute to ``metadata``."""
        # When validating from an ORM model, ``metadata_`` must be copied into
        # the ``metadata`` field before Pydantic processes the object.
        if hasattr(obj, "metadata_"):
            # Build a plain dict to avoid mutating the ORM instance.
            data = {
                "id": obj.id,
                "type": obj.type,
                "actor_type": obj.actor_type,
                "actor_id": obj.actor_id,
                "changes": obj.changes,
                "created_objects": obj.created_objects,
                "deleted_objects": obj.deleted_objects,
                "narrative": obj.narrative,
                "visibility": obj.visibility,
                "proposal_id": obj.proposal_id,
                "parent_event_id": obj.parent_event_id,
                "session_id": obj.session_id,
                "metadata": obj.metadata_,
                "created_at": obj.created_at,
                "targets": obj.targets,
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class UpdateEventVisibilityRequest(BaseModel):
    """Request body for PATCH /api/v1/events/{id}/visibility.

    Attributes
    ----------
    visibility:
        The new visibility level.  Must be one of the 7 canonical levels:
        ``silent``, ``gm_only``, ``private``, ``bonded``, ``familiar``,
        ``public``, ``global``.
    """

    visibility: str

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        """Ensure visibility is one of the 7 canonical levels."""
        if v not in VALID_VISIBILITY_LEVELS:
            raise ValueError(
                f"visibility must be one of: {sorted(VALID_VISIBILITY_LEVELS)}"
            )
        return v
