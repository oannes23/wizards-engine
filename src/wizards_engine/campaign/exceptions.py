"""Campaign import/export exceptions.

These exceptions are raised by the ``NameResolver`` and validation
functions in the campaign import/export system.  They are independent
of the HTTP service-layer exceptions in ``wizards_engine.services.exceptions``.
"""

from __future__ import annotations

__all__ = [
    "CampaignValidationError",
    "DuplicateNameError",
    "UnresolvedReferenceError",
]


class CampaignValidationError(Exception):
    """Base exception for campaign import/export validation errors."""


class DuplicateNameError(CampaignValidationError):
    """Raised when a name is registered twice for the same entity type.

    Parameters
    ----------
    entity_type:
        The entity type (e.g. ``"character"``, ``"group"``).
    name:
        The name that was registered more than once.
    """

    def __init__(self, entity_type: str, name: str) -> None:
        self.entity_type = entity_type
        self.name = name
        super().__init__(
            f"Duplicate name {name!r} for entity type {entity_type!r}."
        )


class UnresolvedReferenceError(CampaignValidationError):
    """Raised when a cross-reference cannot be resolved.

    Parameters
    ----------
    entity_type:
        The entity type that was looked up (e.g. ``"character"``).
    name:
        The name that could not be found in the registry.
    """

    def __init__(self, entity_type: str, name: str) -> None:
        self.entity_type = entity_type
        self.name = name
        super().__init__(
            f"Cannot resolve {entity_type!r} reference {name!r}: "
            f"no entity with that name has been registered."
        )
