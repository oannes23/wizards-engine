"""FastAPI dependency functions for authentication and authorization.

Provides injectable dependencies that routes can declare as parameters:

- ``get_current_user``: reads the ``login_code`` cookie, looks up the user in
  the database, and returns the active User object.  Raises 401 if the cookie
  is missing, invalid, or belongs to an inactive account.
- ``require_role``: factory that returns a dependency enforcing one or more
  allowed roles, raising 403 for callers without a matching role.
- ``require_gm``: pre-built dependency alias — requires the GM role.
- ``require_privileged``: pre-built dependency alias — requires GM or Viewer.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.roles import PRIVILEGED_ROLES, Role


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


def require_role(*allowed: str):
    """Return a FastAPI dependency that requires one of the given roles.

    Usage::

        @router.get("/gm-only", dependencies=[Depends(require_role(Role.GM))])
        @router.get("/gm-or-viewer", dependencies=[Depends(require_role(Role.GM, Role.VIEWER))])

    Args:
        *allowed: One or more :class:`~wizards_engine.roles.Role` values (or
            equivalent strings) that are permitted to call the endpoint.

    Returns:
        A FastAPI dependency callable that accepts the current user and raises
        403 if their role is not in *allowed*.
    """
    allowed_set = frozenset(allowed)

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_set:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "insufficient_role",
                        "message": "This action requires GM privileges.",
                    }
                },
            )
        return current_user

    return _dependency


#: Require the GM role.  Drop-in replacement for the old ``require_gm``.
require_gm = require_role(Role.GM)

#: Require GM **or** Viewer — used on read-only GM endpoints.
require_privileged = require_role(*PRIVILEGED_ROLES)
