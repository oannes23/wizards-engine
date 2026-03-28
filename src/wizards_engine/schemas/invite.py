"""Pydantic schemas for Invite API endpoints.

Covers request and response shapes for the ``/api/v1/game/invites`` resource.
"""

import datetime as _dt

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from wizards_engine.roles import Role


class CreateInviteRequest(BaseModel):
    """Optional request body for POST /game/invites.

    Attributes
    ----------
    role:
        The role to assign to the user who redeems this invite.
        Must be ``"player"`` or ``"viewer"``.  Defaults to ``"player"``.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    role: str = Role.PLAYER

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Ensure role is one of the accepted invite roles.

        Args:
            v: The role string after whitespace stripping.

        Returns:
            The validated role string.

        Raises:
            ValueError: If role is not ``"player"`` or ``"viewer"``.
        """
        if v not in {Role.PLAYER, Role.VIEWER}:
            raise ValueError(f"role must be 'player' or 'viewer', got '{v}'")
        return v


class InviteResponse(BaseModel):
    """Response body for a single Invite resource.

    Returned by POST (201) and each item in the GET list (200).

    Attributes
    ----------
    id:
        ULID primary key.  This IS the shareable code — there is no
        separate code column.
    is_consumed:
        ``True`` if the invite has been redeemed by a player joining.
    role:
        The role the redeemer will receive: ``"player"`` or ``"viewer"``.
    login_url:
        Computed magic link URL: ``/login/{id}``.  The player visits this
        URL to redeem the invite or (after redemption) to log in.
    created_at:
        ISO 8601 UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    is_consumed: bool
    role: str
    created_at: _dt.datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def login_url(self) -> str:
        """Return the magic link URL for this invite code.

        Returns:
            A string of the form ``/login/<id>``.
        """
        return f"/login/{self.id}"
