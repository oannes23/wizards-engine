"""Route handler for POST /api/v1/characters/{id}/recharge-trait.

Player direct action that spends 1 Free Time to restore a trait's charges to 5.

Endpoint
--------
POST /characters/{id}/recharge-trait  — Owner or GM.  Spend 1 FT to fully
recharge one active Core or Role trait slot.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.slot import Slot
from wizards_engine.models.user import User
from wizards_engine.schemas.character import CharacterResponse
from wizards_engine.services.event import create_event

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class RechargeTraitRequest(BaseModel):
    """Request body for the recharge-trait action.

    Attributes
    ----------
    trait_instance_id:
        ULID of the Slot record representing the trait to recharge.
    narrative:
        Player-written description of how the trait is recharged.  Must be
        a non-empty string.
    """

    model_config = ConfigDict(from_attributes=True)

    trait_instance_id: str
    narrative: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/characters/{character_id}/recharge-trait",
    response_model=CharacterResponse,
    status_code=200,
    summary="Recharge Trait — spend 1 Free Time to restore a trait to full charges",
    description=(
        "Player direct action.  Spends 1 Free Time to set a Core or Role trait's "
        "charges back to 5 (full).  "
        "Only full (PC-level) characters may use this action.  "
        "The owning player may call this endpoint; the GM may call it on behalf of "
        "any character.  "
        "Returns 409 if the trait is already at 5 charges (trait_already_full) or "
        "Free Time is 0 (insufficient_free_time).  "
        "Returns 404 if the character or trait is not found.  "
        "Returns 422 if the target slot does not belong to the character, is "
        "inactive, or is not a core_trait or role_trait."
    ),
)
def recharge_trait(
    character_id: str,
    body: RechargeTraitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Recharge a Core or Role trait to full (5 charges) for a full (PC) character.

    Args:
        character_id: ULID of the target character.
        body: Request body containing ``trait_instance_id`` and ``narrative``.
        current_user: Authenticated user.  Must be the character's owning player
            or the GM.
        db: Injected SQLAlchemy session.

    Returns:
        ``CharacterResponse`` with the character's current state after the action.

    Raises:
        HTTPException(404): If the character does not exist or is deleted.
        HTTPException(403): If the caller is neither the GM nor the
            character's owning player.
        HTTPException(422): If the character is not a full (PC-level) character
            (``not_a_pc``), the narrative is empty (``narrative_required``), the
            trait slot is not found (``trait_not_found``), the slot does not
            belong to the character (``trait_not_owned``), the slot is inactive
            (``trait_not_active``), or the slot type is not ``core_trait`` or
            ``role_trait`` (``not_a_trait``).
        HTTPException(409): If the trait is already at 5 charges
            (``trait_already_full``) or Free Time is 0
            (``insufficient_free_time``).
    """
    # ------------------------------------------------------------------
    # 1. Fetch character — must exist and not be deleted
    # ------------------------------------------------------------------
    character: Character | None = db.get(Character, character_id)
    if character is None or character.is_deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Character '{character_id}' not found.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 2. Authorisation — owner or GM
    # ------------------------------------------------------------------
    if current_user.role != "gm" and current_user.character_id != character_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": "You do not have permission to perform this action for this character.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 3. Must be a full (PC-level) character
    # ------------------------------------------------------------------
    if character.detail_level != "full":
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "not_a_pc",
                    "message": "Only full (PC-level) characters can use recharge-trait.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 4. Validate narrative is non-empty
    # ------------------------------------------------------------------
    if not body.narrative or not body.narrative.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "narrative_required",
                    "message": "A non-empty narrative is required for this action.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 5. Fetch the slot by trait_instance_id — must exist
    # ------------------------------------------------------------------
    slot: Slot | None = db.get(Slot, body.trait_instance_id)
    if slot is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "trait_not_found",
                    "message": f"Trait slot '{body.trait_instance_id}' not found.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 6. Validate slot belongs to the character
    # ------------------------------------------------------------------
    if slot.owner_id != character_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "trait_not_owned",
                    "message": "This trait slot does not belong to the specified character.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 7. Validate slot is active
    # ------------------------------------------------------------------
    if not slot.is_active:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "trait_not_active",
                    "message": "Only active traits can be recharged.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 8. Validate slot_type is core_trait or role_trait
    # ------------------------------------------------------------------
    if slot.slot_type not in ("core_trait", "role_trait"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "not_a_trait",
                    "message": "Only core_trait and role_trait slots can be recharged.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 9. Validate charges < 5 (guard against NULL charge)
    # ------------------------------------------------------------------
    charge_before: int = slot.charge if slot.charge is not None else 0
    if charge_before >= 5:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "trait_already_full",
                    "message": "This trait's charges are already at the maximum of 5.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 10. Validate Free Time >= 1
    # ------------------------------------------------------------------
    ft_before: int = character.free_time or 0
    if ft_before < 1:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "insufficient_free_time",
                    "message": "Character does not have enough Free Time (requires 1).",
                }
            },
        )

    # ------------------------------------------------------------------
    # 11. Apply changes
    # ------------------------------------------------------------------
    ft_after = ft_before - 1

    slot.charge = 5
    character.free_time = ft_after
    db.flush()

    # ------------------------------------------------------------------
    # 12. Create event
    # ------------------------------------------------------------------
    create_event(
        db,
        type="player.recharge_trait",
        actor_type="gm" if current_user.role == "gm" else "player",
        actor_id=current_user.id,
        visibility="private",
        narrative=body.narrative,
        changes={
            f"slot.{body.trait_instance_id}.charge": {
                "op": "meter.set",
                "before": charge_before,
                "after": 5,
            },
            f"character.{character_id}.free_time": {
                "op": "meter.delta",
                "before": ft_before,
                "after": ft_after,
            },
        },
        targets=[
            {
                "target_type": "character",
                "target_id": character_id,
                "is_primary": True,
            }
        ],
    )

    # ------------------------------------------------------------------
    # 13. Return updated character
    # ------------------------------------------------------------------
    db.refresh(character)
    return CharacterResponse.model_validate(character)
