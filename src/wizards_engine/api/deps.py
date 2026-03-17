"""FastAPI dependency functions for authentication and authorization.

Provides injectable dependencies that routes can declare as parameters:

- ``get_current_user``: reads the ``login_code`` cookie, looks up the user in
  the database, and returns the active User object.  Raises 401 if the cookie
  is missing, invalid, or belongs to an inactive account.
- ``require_gm``: thin wrapper around ``get_current_user`` that additionally
  enforces the GM role, raising 403 for non-GM callers.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.db import get_db
from wizards_engine.models.user import User


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated User for the current request.

    Reads the ``login_code`` cookie from the incoming request, looks up the
    matching User record, and returns it.  The cookie value is compared against
    the ``login_code`` column using an exact match (plaintext, indexed lookup).

    Raises:
        HTTPException(401): if the cookie is absent (``cookie_missing``),
            does not match any user (``cookie_invalid``), or the matched user
            has ``is_active = False`` (``account_inactive``).

    Args:
        request: The incoming HTTP request (injected by FastAPI).
        db: A SQLAlchemy session (injected via ``get_db``).

    Returns:
        The active User corresponding to the login_code cookie.
    """
    code = request.cookies.get(COOKIE_NAME)
    if not code:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "cookie_missing", "message": "No auth cookie present."}},
        )

    user = db.scalars(select(User).where(User.login_code == code)).first()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "cookie_invalid", "message": "The provided auth cookie is not valid."}},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "account_inactive", "message": "This account has been deactivated."}},
        )

    return user


def require_gm(current_user: User = Depends(get_current_user)) -> User:
    """Require the current user to have the GM role.

    Wraps ``get_current_user`` and additionally checks that the authenticated
    user has ``role = 'gm'``.

    Raises:
        HTTPException(403): if the authenticated user is not the GM
            (``insufficient_role``).

    Args:
        current_user: The authenticated user (injected via ``get_current_user``).

    Returns:
        The authenticated User, guaranteed to have ``role = 'gm'``.
    """
    if current_user.role != "gm":
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "insufficient_role", "message": "This action requires GM privileges."}},
        )
    return current_user
