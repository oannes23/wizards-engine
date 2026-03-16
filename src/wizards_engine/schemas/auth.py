"""Pydantic schemas for authentication-related API endpoints.

Covers the setup endpoint (creating the initial GM account), the /me identity
and profile-update endpoints, and any future auth endpoints such as login,
refresh, etc.
"""

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_display_name(v: str) -> str:
    """Shared display-name validation: non-empty, 1–50 chars after strip.

    Called by Pydantic field validators on any schema that accepts a
    ``display_name`` field.  Assumes ``str_strip_whitespace=True`` is set
    on the model's ConfigDict so *v* arrives pre-stripped.
    """
    if not v:
        raise ValueError("display_name must not be empty")
    if len(v) > 50:
        raise ValueError("display_name must be 50 characters or fewer")
    return v


class SetupRequest(BaseModel):
    """Request body for POST /api/v1/setup."""

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        return _validate_display_name(v)


class MeResponse(BaseModel):
    """Response body for GET /api/v1/me and PATCH /api/v1/me.

    Attributes
    ----------
    id:
        ULID of the authenticated user.
    display_name:
        The user's current display name.
    role:
        ``"gm"`` or ``"player"``.
    character_id:
        ULID of the linked Character, or ``None`` for users without a linked
        character (e.g. the GM).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    role: str
    character_id: str | None


class UpdateMeRequest(BaseModel):
    """Request body for PATCH /api/v1/me."""

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        return _validate_display_name(v)


class SetupResponse(BaseModel):
    """Response body for a successful POST /api/v1/setup.

    Attributes
    ----------
    id:
        ULID of the newly created GM user.
    display_name:
        The GM's display name as stored.
    role:
        Always ``"gm"`` for the setup endpoint.
    login_url:
        Magic link URL the GM can use to authenticate: ``/login/<code>``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    role: str
    login_url: str


class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth/login.

    Attributes
    ----------
    code:
        The raw code string — either a user's ``login_code`` or an invite ``id``.
    """

    code: str


class LoginUserResponse(BaseModel):
    """Response body when login resolves to an active user account.

    Attributes
    ----------
    id:
        ULID of the authenticated user.
    display_name:
        The user's current display name.
    role:
        ``"gm"`` or ``"player"``.
    character_id:
        ULID of the linked Character, or ``None`` for users without a linked
        character (e.g. the GM).
    type:
        Always ``"user"`` — discriminates this response from the invite variant.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    role: str
    character_id: str | None
    type: str = "user"


class LoginInviteResponse(BaseModel):
    """Response body when login resolves to an unconsumed invite.

    Attributes
    ----------
    type:
        Always ``"invite"`` — signals the frontend to redirect to the join form.
    """

    type: str = "invite"


class JoinRequest(BaseModel):
    """Request body for POST /api/v1/game/join.

    Attributes
    ----------
    code:
        The invite code to redeem — must match an unconsumed ``Invite.id``.
    character_name:
        Name for the new Character.  1–200 characters, trimmed, non-empty.
    display_name:
        Display name for the new User.  1–50 characters, trimmed, non-empty.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str
    character_name: str
    display_name: str

    @field_validator("character_name")
    @classmethod
    def validate_character_name(cls, v: str) -> str:
        """Ensure character_name is non-empty and at most 200 characters."""
        if not v:
            raise ValueError("character_name must not be empty")
        if len(v) > 200:
            raise ValueError("character_name must be 200 characters or fewer")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name_field(cls, v: str) -> str:
        """Ensure display_name is non-empty and at most 50 characters."""
        return _validate_display_name(v)


class JoinResponse(BaseModel):
    """Response body for a successful POST /api/v1/game/join.

    Attributes
    ----------
    id:
        ULID of the newly created User.
    display_name:
        The player's display name as stored.
    role:
        Always ``"player"`` for the join endpoint.
    character_id:
        ULID of the newly created Character linked to this User.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    role: str
    character_id: str | None
