"""Service layer for the player join (invite redemption) flow.

Provides a single atomic operation: ``join_game`` redeems an invite code,
creates a User + full Character in one transaction, and returns the new User.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.user import Invite, User
from wizards_engine.roles import Role

__all__ = [
    "InviteNotFoundError",
    "join_game",
]

# ---------------------------------------------------------------------------
# Canonical defaults for a new full (PC-level) character
# ---------------------------------------------------------------------------

_FULL_SKILLS: dict[str, int] = {
    "awareness": 0,
    "composure": 0,
    "influence": 0,
    "finesse": 0,
    "speed": 0,
    "power": 0,
    "knowledge": 0,
    "technology": 0,
}

_FULL_MAGIC_STATS: dict[str, dict[str, int]] = {
    "being": {"level": 0, "xp": 0},
    "wyrding": {"level": 0, "xp": 0},
    "summoning": {"level": 0, "xp": 0},
    "enchanting": {"level": 0, "xp": 0},
    "dreaming": {"level": 0, "xp": 0},
}


class InviteNotFoundError(Exception):
    """Raised when the provided invite code is invalid or already consumed.

    The caller should surface this as a 404 with code ``invite_not_found``.
    The same exception type is used for all invalid-invite cases so that the
    response does not leak whether a code exists in the database.
    """


def join_game(
    db: Session,
    *,
    code: str,
    character_name: str | None = None,
    display_name: str,
) -> User:
    """Atomically redeem an invite code and create a User (+ Character for players).

    Validates the invite (exists, unconsumed), then in a single flush:

    1. Marks the invite as consumed.
    2. If the invite role is ``"player"``: creates a new full Character with all
       mechanical fields at zero.
    3. Creates a new User with the invite's role, ``login_code`` set to the
       invite code (same string), and ``character_id`` linked to the new
       character (or ``None`` for viewers).

    The caller is responsible for committing or rolling back the session.

    Args:
        db: Active SQLAlchemy session.
        code: The raw invite code (must match an unconsumed ``Invite.id``).
        character_name: Name for the new Character (already validated by caller).
            Required when the invite role is ``"player"``; ignored for viewers.
        display_name: Display name for the new User (already validated by caller).

    Returns:
        The newly created :class:`~wizards_engine.models.user.User` instance
        with ``id`` populated.  ``character_id`` is non-null for players,
        ``None`` for viewers.

    Raises:
        InviteNotFoundError: For all invalid invite cases — missing, already
            consumed, or any other rejection reason — so the response does not
            reveal whether the code exists.
        ValueError: If the invite is for a player but ``character_name`` is
            not provided.
    """
    # --- Validate invite: exists and unconsumed ---
    invite = db.scalars(
        select(Invite).where(Invite.id == code, Invite.is_consumed.is_(False))
    ).first()
    if invite is None:
        raise InviteNotFoundError(code)

    # --- Mark invite consumed ---
    invite.is_consumed = True
    db.flush()

    role = invite.role  # "player" or "viewer"

    # --- Create Character for player invites ---
    character_id = None
    if role == Role.PLAYER:
        if not character_name:
            raise ValueError("character_name is required for player invites")
        character = Character(
            name=character_name,
            detail_level="full",
            stress=0,
            free_time=0,
            plot=0,
            gnosis=0,
            skills=dict(_FULL_SKILLS),
            magic_stats={k: dict(v) for k, v in _FULL_MAGIC_STATS.items()},
            last_session_time_now=0,
            is_deleted=False,
        )
        db.add(character)
        db.flush()  # populate character.id before FK reference below
        character_id = character.id

    # --- Create the User ---
    user = User(
        display_name=display_name,
        role=role,
        login_code=code,  # invite code becomes the permanent login code
        is_active=True,
        character_id=character_id,
    )
    db.add(user)
    db.flush()
    db.refresh(user)

    return user
