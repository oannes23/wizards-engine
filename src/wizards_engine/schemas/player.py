"""Pydantic schemas for Player Roster API endpoints.

Covers response shapes for the ``/api/v1/players`` resource.

Two response shapes are defined to support the role-conditional requirement:
- ``PlayerResponse`` — returned for non-GM callers; omits ``login_url``.
- ``PlayerGMResponse`` — returned for GM callers; includes ``login_url``.

Both are collected in ``PlayerListResponse`` and ``PlayerGMListResponse``
respectively, though the route constructs the list directly from the appropriate
model based on the caller's role.
"""

from pydantic import BaseModel, ConfigDict


class PlayerResponse(BaseModel):
    """Response body for a single Player entry (non-GM callers).

    Attributes
    ----------
    id:
        ULID primary key.
    display_name:
        Player's display name (1–50 characters).
    role:
        ``"gm"``, ``"player"``, or ``"viewer"``.
    character_id:
        ULID of the linked Character, or ``None`` if the user has no character
        (e.g. a GM who has not created a character).
    is_active:
        Whether the account is active.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    role: str
    character_id: str | None
    is_active: bool


class PlayerGMResponse(PlayerResponse):
    """Response body for a single Player entry (GM callers only).

    Extends ``PlayerResponse`` with the ``login_url`` field so the GM can
    view and share each player's magic link.

    Attributes
    ----------
    login_url:
        The magic link URL for this player, formatted as ``/login/<login_code>``.
    """

    login_url: str
