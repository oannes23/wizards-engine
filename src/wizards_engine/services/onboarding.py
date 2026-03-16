"""Service layer for the player join (invite redemption) flow.

Provides a single atomic operation: ``join_game`` redeems an invite code,
creates a User + full Character in one transaction, and returns the new User.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.user import Invite, User

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
    character_name: str,
    display_name: str,
) -> User:
    """Atomically redeem an invite code and create a User + full Character.

    Validates the invite (exists, unconsumed), then in a single flush:

    1. Marks the invite as consumed.
    2. Creates a new full Character with all mechanical fields at zero.
    3. Creates a new User with ``role = "player"``, ``login_code`` set to the
       invite code (same string), and ``character_id`` linked to the new
       character.

    The caller is responsible for committing or rolling back the session.

    Args:
        db: Active SQLAlchemy session.
        code: The raw invite code (must match an unconsumed ``Invite.id``).
        character_name: Name for the new Character (already validated by caller).
        display_name: Display name for the new User (already validated by caller).

    Returns:
        The newly created :class:`~wizards_engine.models.user.User` instance
        with ``id`` and ``character_id`` populated.

    Raises:
        InviteNotFoundError: For all invalid invite cases — missing, already
            consumed, or any other rejection reason — so the response does not
            reveal whether the code exists.
    """
    # --- Validate invite: exists and unconsumed ---
    invite = (
        db.query(Invite)
        .filter(Invite.id == code, Invite.is_consumed.is_(False))
        .first()
    )
    if invite is None:
        raise InviteNotFoundError(code)

    # --- Mark invite consumed ---
    invite.is_consumed = True
    db.flush()

    # --- Create the full Character ---
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

    # --- Create the User linked to the Character ---
    user = User(
        display_name=display_name,
        role="player",
        login_code=code,  # invite code becomes the permanent login code
        is_active=True,
        character_id=character.id,
    )
    db.add(user)
    db.flush()
    db.refresh(user)

    return user
