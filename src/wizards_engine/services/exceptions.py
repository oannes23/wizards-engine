"""Domain exceptions for the service layer.

These exceptions decouple service logic from HTTP concerns.  Route handlers
and app-level exception handlers catch them and translate to the appropriate
HTTP responses.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "NotFoundError",
    "ForbiddenError",
    "BusinessRuleViolation",
    "ProposalNotPending",
    "InsufficientResources",
]


class NotFoundError(Exception):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity: str, entity_id: str, *, code: str = "not_found") -> None:
        self.entity = entity
        self.entity_id = entity_id
        self.code = code
        super().__init__(f"{entity} '{entity_id}' not found.")


class ForbiddenError(Exception):
    """Raised when the caller lacks permission for the requested action."""

    def __init__(self, message: str = "You do not have permission to perform this action.", *, code: str = "forbidden") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class BusinessRuleViolation(Exception):
    """Raised when a business rule or validation constraint is violated.

    Maps to HTTP 422 in the standard error envelope.
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)

    @classmethod
    def field_error(cls, field: str, message: str) -> BusinessRuleViolation:
        """Create a validation-style error for a specific field."""
        return cls(
            "validation_error",
            "Validation failed",
            {"fields": {field: message}},
        )


class ProposalNotPending(Exception):
    """Raised when an operation requires a pending proposal but it is not."""

    def __init__(self, proposal_id: str) -> None:
        self.proposal_id = proposal_id
        super().__init__(f"Proposal '{proposal_id}' is not in pending status.")


class InsufficientResources(Exception):
    """Raised when a character lacks the resources required for an action."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)
