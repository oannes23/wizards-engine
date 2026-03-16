"""Route handlers for Magic Effect player direct action endpoints.

Players can use charged effects (decrement a charge) and retire their own
effects (move to Past) directly — no GM approval needed.

Endpoints
---------
POST  /characters/{character_id}/effects/{effect_id}/use    — Player (owner) or GM.
POST  /characters/{character_id}/effects/{effect_id}/retire — Player (owner) or GM.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.db import get_db
from wizards_engine.models.user import User
from wizards_engine.schemas.character import MagicEffectResponse
from wizards_engine.schemas.magic_effect import UseEffectRequest
from wizards_engine.services import magic_effect as magic_effect_svc

router = APIRouter()


def _check_effect_ownership(
    current_user: User,
    character_id: str,
    effect_character_id: str,
    effect_id: str,
) -> None:
    """Raise 403 if the caller is not the GM and does not own the character.

    Args:
        current_user: The authenticated user.
        character_id: The character_id from the URL path.
        effect_character_id: The character_id stored on the effect record.
        effect_id: ULID of the effect (used in error messages).

    Raises:
        HTTPException(403): If the caller is not the GM and their linked
            character is not ``character_id``.
    """
    if current_user.role == "gm":
        return
    if current_user.character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": "You do not have permission to act on this character's effects.",
                }
            },
        )


@router.post(
    "/characters/{character_id}/effects/{effect_id}/use",
    response_model=MagicEffectResponse,
    status_code=200,
    summary="Use a charged magic effect",
    description=(
        "Player direct action — no GM approval required.  "
        "Decrements ``charges_current`` by 1.  "
        "Requires the effect to be active, of type ``'charged'``, and have "
        "``charges_current > 0``.  "
        "The owning player (or the GM) may invoke this endpoint.  "
        "The optional ``narrative`` field is accepted for event-log purposes "
        "but does not affect the charge decrement."
    ),
)
def use_effect(
    character_id: str,
    effect_id: str,
    body: UseEffectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MagicEffectResponse:
    """Decrement a charged effect's charges by 1.

    Args:
        character_id: ULID of the character who owns the effect.
        effect_id: ULID of the MagicEffect to use.
        body: Optional narrative text describing the use.
        current_user: Authenticated user (must own the character or be GM).
        db: Injected SQLAlchemy session.

    Returns:
        ``MagicEffectResponse`` with the updated ``charges_current``.

    Raises:
        HTTPException(404): If the effect does not exist or does not belong to
            ``character_id``.
        HTTPException(403): If the caller is not the GM or the character's owner.
        HTTPException(409): If the effect has no charges remaining.
        HTTPException(400): If the effect is not of type ``'charged'`` or is not active.
    """
    effect = magic_effect_svc.get_effect(db, effect_id)
    if effect is None or effect.character_id != character_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Magic effect '{effect_id}' not found on character '{character_id}'.",
                }
            },
        )

    _check_effect_ownership(current_user, character_id, effect.character_id, effect_id)

    if not effect.is_active:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "effect_not_active",
                    "message": f"Magic effect '{effect_id}' has been retired and cannot be used.",
                }
            },
        )

    if effect.effect_type != "charged":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "effect_not_charged",
                    "message": (
                        f"Magic effect '{effect_id}' is of type '{effect.effect_type}'. "
                        "Only charged effects can be used this way."
                    ),
                }
            },
        )

    if effect.charges_current is None or effect.charges_current <= 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "no_charges_remaining",
                    "message": f"Magic effect '{effect_id}' has no charges remaining.",
                }
            },
        )

    updated = magic_effect_svc.use_effect(db, effect_id, narrative=body.narrative)
    return MagicEffectResponse.model_validate(updated)


@router.post(
    "/characters/{character_id}/effects/{effect_id}/retire",
    response_model=MagicEffectResponse,
    status_code=200,
    summary="Retire a magic effect",
    description=(
        "Player direct action — no GM approval required.  "
        "Sets ``is_active = false``, moving the effect to the character's Past "
        "section and freeing one slot toward the cap of 9.  "
        "The owning player (or the GM) may invoke this endpoint.  "
        "Empty body — no fields required."
    ),
)
def retire_effect(
    character_id: str,
    effect_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MagicEffectResponse:
    """Set an effect's is_active flag to False (move to Past).

    Args:
        character_id: ULID of the character who owns the effect.
        effect_id: ULID of the MagicEffect to retire.
        current_user: Authenticated user (must own the character or be GM).
        db: Injected SQLAlchemy session.

    Returns:
        ``MagicEffectResponse`` with ``is_active = false``.

    Raises:
        HTTPException(404): If the effect does not exist or does not belong to
            ``character_id``.
        HTTPException(403): If the caller is not the GM or the character's owner.
    """
    effect = magic_effect_svc.get_effect(db, effect_id)
    if effect is None or effect.character_id != character_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Magic effect '{effect_id}' not found on character '{character_id}'.",
                }
            },
        )

    _check_effect_ownership(current_user, character_id, effect.character_id, effect_id)

    updated = magic_effect_svc.retire_effect(db, effect_id)
    return MagicEffectResponse.model_validate(updated)
