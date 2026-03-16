"""Pydantic schemas for Session API endpoints.

Covers create, update, list-query, and response shapes for the
``/api/v1/sessions`` resource.
"""

import datetime as _dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/v1/sessions.

    All fields are optional.  The session is always created with
    ``status = "draft"`` regardless of what is sent.

    Attributes
    ----------
    time_now:
        Optional abstract campaign time counter (integer).
    date:
        Optional date (YYYY-MM-DD) for when the session takes/took place.
    summary:
        Optional session summary text.
    notes:
        Optional GM notes.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    time_now: int | None = None
    date: _dt.date | None = None
    summary: str | None = None
    notes: str | None = None


class UpdateSessionRequest(BaseModel):
    """Request body for PATCH /api/v1/sessions/{id}.

    Only fields present in the request body are applied (exclude_unset
    semantics).  Sending ``null`` for a nullable field clears it.

    Permitted only when session ``status`` is ``draft`` or ``active``.
    Ended sessions return 400.

    Attributes
    ----------
    time_now:
        New abstract campaign time counter, or ``null`` to clear.
    date:
        New session date, or ``null`` to clear.
    summary:
        New summary text, or ``null`` to clear.
    notes:
        New notes text, or ``null`` to clear.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    time_now: Annotated[int | None, Field(default=None)]
    date: _dt.date | None = None
    summary: str | None = None
    notes: str | None = None


class AddParticipantRequest(BaseModel):
    """Request body for POST /api/v1/sessions/{id}/participants.

    Players send their own ``character_id``.  The GM can send any
    ``character_id``.  Server validates ownership for non-GM callers.

    Attributes
    ----------
    character_id:
        ULID of the character to register.
    additional_contribution:
        Whether the participant is flagging an Additional Contribution.
        Defaults to ``False``.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    character_id: str
    additional_contribution: bool = False


class UpdateParticipantRequest(BaseModel):
    """Request body for PATCH /api/v1/sessions/{id}/participants/{character_id}.

    Only allowed when the session is in ``draft`` status.

    Attributes
    ----------
    additional_contribution:
        New value for the Additional Contribution flag.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    additional_contribution: bool


class ParticipantResponse(BaseModel):
    """Response shape for a single session participant record.

    Attributes
    ----------
    session_id:
        ULID of the session this participant belongs to.
    character_id:
        ULID of the registered character.
    additional_contribution:
        Whether the participant flagged an Additional Contribution.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    character_id: str
    additional_contribution: bool


class SessionResponse(BaseModel):
    """Response body for a single Session resource.

    Returned by POST (201), GET detail (200), and PATCH (200).

    Attributes
    ----------
    id:
        ULID primary key.
    status:
        Lifecycle state: ``draft``, ``active``, or ``ended``.
    time_now:
        Abstract campaign time counter, or ``null`` if not set.
    date:
        Session date (YYYY-MM-DD), or ``null`` if not set.
    summary:
        Session summary text, or ``null``.
    notes:
        GM notes, or ``null``.
    participants:
        List of registered participant records (empty for new sessions).
    created_at:
        ISO 8601 UTC creation timestamp.
    updated_at:
        ISO 8601 UTC last-modified timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    time_now: int | None
    date: _dt.date | None
    summary: str | None
    notes: str | None
    participants: list[ParticipantResponse]
    created_at: _dt.datetime
    updated_at: _dt.datetime


# SessionListResponse is an alias for SessionResponse — identical shape.
SessionListResponse = SessionResponse
