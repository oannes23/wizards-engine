"""Centralised role constants for the Wizards Engine.

Provides a ``Role`` enum, convenience sets for permission checks, and
helper functions used by the auth and visibility layers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wizards_engine.models.user import User

__all__ = [
    "Role",
    "PRIVILEGED_ROLES",
    "actor_type_for",
    "has_full_visibility",
]


class Role(StrEnum):
    """User roles recognised by the system."""

    GM = "gm"
    PLAYER = "player"
    VIEWER = "viewer"


#: Roles that can see all game state (GM + Viewer).
PRIVILEGED_ROLES: frozenset[str] = frozenset({Role.GM, Role.VIEWER})


def has_full_visibility(user: User) -> bool:
    """Return ``True`` if *user* can see all game state (GM or Viewer)."""
    return user.role in PRIVILEGED_ROLES


def actor_type_for(user: User) -> str:
    """Map a user's role to the ``actor_type`` event field.

    Only GM and Player produce events.  Calling this for a Viewer raises
    ``ValueError`` as a safety net — viewers should never reach event-
    producing code paths.
    """
    if user.role == Role.GM:
        return "gm"
    if user.role == Role.PLAYER:
        return "player"
    raise ValueError(f"Role {user.role!r} cannot produce events")
