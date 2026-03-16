"""Shared Pydantic models used across all API endpoints.

Provides the standard error envelope and generic paginated list response
that every route in Wizards Engine uses for consistent response shapes.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Structured detail block carried inside every error response.

    Attributes
    ----------
    code:
        Machine-readable error code (e.g. ``"not_found"``, ``"validation_error"``).
    message:
        Human-readable description of the error.
    details:
        Optional mapping of extra context (e.g. per-field validation messages).
    """

    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    """Top-level error envelope returned by all error responses.

    All error responses wrap a single :class:`ErrorDetail` under the ``error``
    key so that clients always have a uniform shape to parse regardless of
    status code.
    """

    model_config = ConfigDict(from_attributes=True)

    error: ErrorDetail


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list response for ULID-cursor-based pagination.

    Attributes
    ----------
    items:
        The current page of results.
    next_cursor:
        The ULID of the last item on this page.  Pass as the ``after``
        query parameter to fetch the next page.  ``None`` when this is
        the last page.
    has_more:
        ``True`` when additional pages exist beyond this one.
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    next_cursor: str | None
    has_more: bool
