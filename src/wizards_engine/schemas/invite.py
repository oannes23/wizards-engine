"""Pydantic schemas for Invite API endpoints.

Covers response shapes for the ``/api/v1/game/invites`` resource.
There is no request body for POST — the GM generates bare invites
with no configuration options.
"""

import datetime as _dt

from pydantic import BaseModel, ConfigDict, computed_field


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
    login_url:
        Computed magic link URL: ``/login/{id}``.  The player visits this
        URL to redeem the invite or (after redemption) to log in.
    created_at:
        ISO 8601 UTC creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    is_consumed: bool
    created_at: _dt.datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def login_url(self) -> str:
        """Return the magic link URL for this invite code.

        Returns:
            A string of the form ``/login/<id>``.
        """
        return f"/login/{self.id}"
