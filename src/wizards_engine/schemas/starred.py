"""Pydantic schemas for the Starring API endpoints.

Covers request and response shapes for:
- GET  /api/v1/me/starred
- POST /api/v1/me/starred
- DELETE /api/v1/me/starred/{type}/{id}
"""

from pydantic import BaseModel, field_validator

VALID_OBJECT_TYPES = {"character", "group", "location"}


class StarRequest(BaseModel):
    """Request body for POST /api/v1/me/starred.

    Attributes
    ----------
    type:
        The Game Object type to star.  Must be one of ``character``,
        ``group``, or ``location``.
    id:
        The ULID of the Game Object to star.
    """

    type: str
    id: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Ensure type is one of the three valid Game Object types."""
        if v not in VALID_OBJECT_TYPES:
            raise ValueError(
                f"type must be one of: {', '.join(sorted(VALID_OBJECT_TYPES))}"
            )
        return v


class StarredObjectResponse(BaseModel):
    """Response body for a single starred Game Object.

    Returned by GET /api/v1/me/starred (list items) and
    POST /api/v1/me/starred (star confirmation).

    Attributes
    ----------
    type:
        The Game Object type: ``character``, ``group``, or ``location``.
    id:
        The ULID of the starred Game Object.
    name:
        The display name of the Game Object, resolved from the corresponding
        table at query time.
    """

    type: str
    id: str
    name: str
