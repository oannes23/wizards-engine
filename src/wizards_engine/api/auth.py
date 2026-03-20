"""Auth helper utilities for setting and clearing the login_code cookie.

These helpers encapsulate the cookie policy (httpOnly, Secure, SameSite=Lax,
persistent) so that every route that touches the auth cookie uses consistent
settings.
"""

import os

from fastapi import Response

COOKIE_NAME = "login_code"

# One year in seconds — effectively permanent. Login codes never expire
# (spec: "permanent until refreshed"), so the cookie should survive browser
# restarts.
_MAX_AGE = 365 * 24 * 60 * 60

# Controls the Secure flag on the auth cookie. Default ``True`` (HTTPS-only).
# Set ``WIZARDS_COOKIE_SECURE=false`` in the environment for local HTTP dev.
_COOKIE_SECURE = os.environ.get("WIZARDS_COOKIE_SECURE", "true").lower() in (
    "true", "1", "yes",
)


def set_auth_cookie(response: Response, login_code: str) -> None:
    """Set the auth cookie on a response.

    The cookie is:
    - httpOnly: not accessible from JavaScript
    - secure: only sent over HTTPS
    - samesite="lax": prevents CSRF while allowing navigation links to work
    - max_age=1 year: persistent across browser restarts (per spec: codes
      never expire, permanent until refreshed)

    Args:
        response: The FastAPI Response object to set the cookie on.
        login_code: The raw login code value to store in the cookie.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=login_code,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=_MAX_AGE,
    )


def clear_auth_cookie(response: Response) -> None:
    """Remove the auth cookie from a response.

    Deletes the cookie by name so the client discards it on receipt.

    Args:
        response: The FastAPI Response object to clear the cookie on.
    """
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
    )
