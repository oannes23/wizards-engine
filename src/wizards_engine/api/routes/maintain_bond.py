"""Route handler for POST /api/v1/characters/{id}/maintain-bond.

Player direct action that spends 1 Free Time to restore a bond's charges to
its effective maximum (5 - degradations).

Endpoint
--------
POST /characters/{id}/maintain-bond  — Owner or GM.  Spend 1 FT to restore
one active PC bond slot to full charges.
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


class MaintainBondRequest(BaseModel):
    """Request body for the maintain-bond action.

    Attributes
    ----------
    bond_instance_id:
        ULID of the Slot record representing the bond to maintain.
    narrative:
        Player-written description of how the bond is maintained.  Must be
        a non-empty string.
    """

    model_config = ConfigDict(from_attributes=True)

    bond_instance_id: str
    narrative: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/characters/{character_id}/maintain-bond",
    response_model=CharacterResponse,
    status_code=200,
    summary="Maintain Bond — spend 1 Free Time to restore a bond to its effective maximum charges",
    description=(
        "Player direct action.  Spends 1 Free Time to set a PC bond's charges "
        "back to its effective maximum (5 - degradations).  "
        "Only full (PC-level) characters may use this action.  "
        "The owning player may call this endpoint; the GM may call it on behalf of "
        "any character.  "
        "Returns 409 if the bond is already at effective max charges "
        "(bond_already_maintained) or Free Time is 0 (insufficient_free_time).  "
        "Returns 404 if the character or bond is not found.  "
        "Returns 422 if the target slot does not belong to the character, is "
        "inactive, is not a pc_bond, or is a trauma bond."
    ),
)
def maintain_bond(
    character_id: str,
    body: MaintainBondRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Restore a PC bond to its effective maximum charges for a full (PC) character.

    Args:
        character_id: ULID of the target character.
        body: Request body containing ``bond_instance_id`` and ``narrative``.
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
            bond slot is not found (``bond_not_found``), the slot does not
            belong to the character (``bond_not_owned``), the slot is inactive
            (``bond_not_active``), the slot type is not ``pc_bond``
            (``not_a_pc_bond``), or the bond is a trauma bond
            (``cannot_maintain_trauma``).
        HTTPException(409): If the bond is already at effective max charges
            (``bond_already_maintained``) or Free Time is 0
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
                    "message": "Only full (PC-level) characters can use maintain-bond.",
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
    # 5. Fetch the slot by bond_instance_id — must exist
    # ------------------------------------------------------------------
    slot: Slot | None = db.get(Slot, body.bond_instance_id)
    if slot is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "bond_not_found",
                    "message": f"Bond slot '{body.bond_instance_id}' not found.",
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
                    "code": "bond_not_owned",
                    "message": "This bond slot does not belong to the specified character.",
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
                    "code": "bond_not_active",
                    "message": "Only active bonds can be maintained.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 8. Validate slot_type is pc_bond
    # ------------------------------------------------------------------
    if slot.slot_type != "pc_bond":
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "not_a_pc_bond",
                    "message": "Only pc_bond slots can be maintained.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 9. Validate bond is not a trauma bond
    # ------------------------------------------------------------------
    if slot.is_trauma is True:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "cannot_maintain_trauma",
                    "message": "Trauma bonds cannot be maintained.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 10. Compute effective max and validate charges < effective_max
    # ------------------------------------------------------------------
    effective_max: int = 5 - (slot.degradations or 0)
    charges_before: int = slot.charges if slot.charges is not None else 0

    if charges_before >= effective_max:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "bond_already_maintained",
                    "message": "This bond's charges are already at the effective maximum.",
                }
            },
        )

    # ------------------------------------------------------------------
    # 11. Validate Free Time >= 1
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
    # 12. Apply changes
    # ------------------------------------------------------------------
    ft_after = ft_before - 1

    slot.charges = effective_max
    character.free_time = ft_after
    db.flush()

    # ------------------------------------------------------------------
    # 13. Create event
    # ------------------------------------------------------------------
    create_event(
        db,
        type="player.maintain_bond",
        actor_type="gm" if current_user.role == "gm" else "player",
        actor_id=current_user.id,
        visibility="private",
        narrative=body.narrative,
        changes={
            f"slot.{body.bond_instance_id}.charges": {
                "op": "meter.set",
                "before": charges_before,
                "after": effective_max,
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
    # 14. Return updated character
    # ------------------------------------------------------------------
    db.refresh(character)
    return CharacterResponse.model_validate(character)
