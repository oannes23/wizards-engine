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


def _build_changes_summary(changes: dict[str, Any]) -> str | None:
    """Derive a human-readable summary from a changes dict.

    Each key in ``changes`` follows the convention ``{type}.{id}.{field}``
    (e.g. ``character.01ABC.stress``).  Values are dicts containing at
    minimum ``"before"`` and ``"after"`` keys.  Entries that do not have
    both keys are skipped.

    The label for each entry is the last dot-separated segment of the key
    (the field name), title-cased.

    Parameters
    ----------
    changes:
        The ``changes`` dict from an ``Event`` ORM instance.

    Returns
    -------
    str | None
        A comma-separated summary string such as ``"Stress: 3 → 5, Plot: 5 → 3"``,
        or ``None`` if the dict is empty or contains no before/after entries.
    """
    if not changes:
        return None

    parts: list[str] = []
    for key, value in changes.items():
        if not isinstance(value, dict):
            continue
        if "before" not in value or "after" not in value:
            continue
        # Extract the field label from the last segment of the dotted key.
        field_label = key.split(".")[-1].replace("_", " ").title()
        parts.append(f"{field_label}: {value['before']} \u2192 {value['after']}")

    return ", ".join(parts) if parts else None


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
    actor_name:
        Display name of the acting user (from ``User.display_name``), or
        ``None`` for system-generated events.  Denormalized for read
        convenience — resolved at serialization time.
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
    primary_target_name:
        Name of the primary target game object (first entry with
        ``is_primary=True`` in ``event_targets``), or ``None`` if the event
        has no targets.  Denormalized for read convenience.
    primary_target_type:
        Type string of the primary target (e.g. ``"character"``), or
        ``None`` if no primary target exists.
    changes_summary:
        Human-readable summary derived from the ``changes`` dict.  Format:
        ``"{field}: {before} → {after}"``, joined with ``", "``.  ``None``
        when the changes dict is empty or lacks before/after values.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    actor_type: str
    actor_id: str | None
    actor_name: str | None = None
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
    primary_target_name: str | None = None
    primary_target_type: str | None = None
    changes_summary: str | None = None

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Override to remap ``metadata_`` ORM attribute to ``metadata``.

        Also computes ``changes_summary`` from the ``changes`` dict.
        The denormalized ``actor_name``, ``primary_target_name``, and
        ``primary_target_type`` fields default to ``None`` and must be
        populated via :meth:`from_event` when DB access is available.
        """
        # When validating from an ORM model, ``metadata_`` must be copied into
        # the ``metadata`` field before Pydantic processes the object.
        if hasattr(obj, "metadata_"):
            changes = obj.changes or {}
            # Build a plain dict to avoid mutating the ORM instance.
            data = {
                "id": obj.id,
                "type": obj.type,
                "actor_type": obj.actor_type,
                "actor_id": obj.actor_id,
                "actor_name": None,
                "changes": changes,
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
                "primary_target_name": None,
                "primary_target_type": None,
                "changes_summary": _build_changes_summary(changes),
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)

    @classmethod
    def from_event(cls, db, event) -> "EventResponse":
        """Build a full ``EventResponse``, resolving denormalized name fields.

        Performs lightweight DB lookups for the actor display name and the
        primary target's name.  This method is the preferred way to serialize
        events when a DB session is available (e.g. in route handlers).

        Parameters
        ----------
        db:
            An active SQLAlchemy ``Session`` used for name lookups.
        event:
            An ``Event`` ORM instance with ``targets`` already loaded.

        Returns
        -------
        EventResponse
            Fully populated response including ``actor_name``,
            ``primary_target_name``, ``primary_target_type``, and
            ``changes_summary``.
        """
        from wizards_engine.models.character import Character
        from wizards_engine.models.group import Group
        from wizards_engine.models.location import Location

        changes = event.changes or {}

        # Resolve actor display name.
        actor_name: str | None = None
        if event.actor_id is not None and event.actor is not None:
            actor_name = event.actor.display_name

        # Resolve primary target name and type.
        primary_target_name: str | None = None
        primary_target_type: str | None = None
        primary_target = next(
            (t for t in (event.targets or []) if t.is_primary), None
        )
        if primary_target is not None:
            primary_target_type = primary_target.target_type
            _type_to_model = {
                "character": Character,
                "group": Group,
                "location": Location,
            }
            model_cls = _type_to_model.get(primary_target.target_type)
            if model_cls is not None:
                obj = db.get(model_cls, primary_target.target_id)
                if obj is not None:
                    primary_target_name = obj.name

        data = {
            "id": event.id,
            "type": event.type,
            "actor_type": event.actor_type,
            "actor_id": event.actor_id,
            "actor_name": actor_name,
            "changes": changes,
            "created_objects": event.created_objects,
            "deleted_objects": event.deleted_objects,
            "narrative": event.narrative,
            "visibility": event.visibility,
            "proposal_id": event.proposal_id,
            "parent_event_id": event.parent_event_id,
            "session_id": event.session_id,
            "metadata": event.metadata_,
            "created_at": event.created_at,
            "targets": event.targets,
            "primary_target_name": primary_target_name,
            "primary_target_type": primary_target_type,
            "changes_summary": _build_changes_summary(changes),
        }
        return super().model_validate(data)


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
