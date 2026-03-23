"""Route handlers for /api/v1/characters — Character CRUD endpoints.

Provides standard CRUD for the Character resource (both PCs and NPCs).
GM-created characters always have ``detail_level = 'simplified'``.  Full
(PC-level) characters are created via the invite/join flow.

Endpoints
---------
POST   /characters          — GM only.  Create a simplified character.
GET    /characters          — Authenticated.  List with filters + pagination.
GET    /characters/summary  — Authenticated.  Compact PC overview (meters only).
GET    /characters/{id}     — Authenticated.  Character detail (incl. soft-deleted).
PATCH  /characters/{id}     — Owner or GM.  Update name/description/notes.
DELETE /characters/{id}     — GM only.  Soft delete.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_forbidden, raise_not_found, validation_error_response
from wizards_engine.api.types import UlidStr
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import SessionParticipant
from wizards_engine.models.slot import Slot
from wizards_engine.models.user import User
from wizards_engine.schemas.bond import BondGroups
from wizards_engine.schemas.character import (
    CharacterDetailResponse,
    CharacterResponse,
    CharacterTraitGroups,
    CharacterTraitResponse,
    CreateCharacterRequest,
    LocationTiers,
    MagicEffectGroups,
    MagicEffectResponse,
    UpdateCharacterRequest,
)
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.services import character as character_svc
from wizards_engine.services.bond import get_bonds_display_for_entity
from wizards_engine.services.presence import get_locations_for_character

router = APIRouter()


# ---------------------------------------------------------------------------
# Summary schemas — defined here because they are router-local and small
# ---------------------------------------------------------------------------


class CharacterSummaryItem(BaseModel):
    """Compact PC overview item returned by GET /characters/summary.

    Attributes
    ----------
    id:
        ULID primary key of the character.
    name:
        Character display name.
    stress:
        Current Stress meter value (0 if null in DB).
    free_time:
        Current Free Time resource (0 if null in DB).
    plot:
        Current Plot resource (0 if null in DB).
    gnosis:
        Current Gnosis resource (0 if null in DB).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    stress: int
    free_time: int
    plot: int
    gnosis: int


class CharactersSummaryResponse(BaseModel):
    """Response body for GET /characters/summary.

    Attributes
    ----------
    items:
        Ordered list of compact PC summaries, sorted by name ascending.
    """

    items: list[CharacterSummaryItem]


@router.post(
    "/characters",
    response_model=CharacterResponse,
    status_code=201,
    summary="Create a character",
    description=(
        "GM only.  Creates a new simplified (NPC-level) character.  "
        "``detail_level`` is always ``simplified`` for GM-created characters; "
        "full (PC) characters are created via the invite/join flow."
    ),
)
def create_character(
    body: CreateCharacterRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Create a new simplified character.

    Args:
        body: Validated request body with name and optional fields.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``CharacterResponse`` for the newly created character (201).
    """
    character = character_svc.create_character(
        db,
        name=body.name,
        description=body.description,
        notes=body.notes,
        attributes=body.attributes,
    )
    return CharacterResponse.model_validate(character)


@router.get(
    "/characters",
    response_model=PaginatedResponse[CharacterResponse],
    status_code=200,
    summary="List characters",
    description=(
        "Returns a paginated list of characters.  Soft-deleted characters are "
        "excluded by default.  Supports filtering by detail_level, has_player, "
        "name (case-insensitive partial), and include_deleted.  "
        "ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_characters(
    detail_level: str | None = None,
    has_player: bool | None = None,
    include_deleted: bool = False,
    name: str | None = None,
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[CharacterResponse]:
    """Return a paginated, filtered list of characters.

    Args:
        detail_level: Optional filter — ``"full"`` or ``"simplified"``.
        has_player: Optional filter — ``true`` = only chars with a linked user,
            ``false`` = only chars without one.
        include_deleted: When ``true``, include soft-deleted characters.
        name: Case-insensitive partial name filter.
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``CharacterResponse`` objects.
    """
    if detail_level is not None and detail_level not in ("full", "simplified"):
        return validation_error_response(
            {"detail_level": "must be 'full' or 'simplified'"}
        )

    q = character_svc.list_characters_query(
        db,
        detail_level=detail_level,
        has_player=has_player,
        include_deleted=include_deleted,
        name=name,
    )

    page = paginate(db, q, model=Character, after=after, limit=limit)

    return PaginatedResponse[CharacterResponse](
        items=[CharacterResponse.model_validate(c) for c in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get(
    "/characters/summary",
    response_model=CharactersSummaryResponse,
    status_code=200,
    summary="Characters summary — compact PC overview",
    description=(
        "Returns a compact list of all active full (PC-level) characters with "
        "their current meter values: stress, free_time, plot, and gnosis.  "
        "Soft-deleted characters and simplified (NPC) characters are excluded.  "
        "Results are sorted by name ascending.  "
        "Available to any authenticated user (player or GM)."
    ),
)
def characters_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharactersSummaryResponse:
    """Return compact summaries of all active PCs.

    Queries for all non-deleted full characters and returns a minimal
    subset of fields — just the four meter columns plus id and name.
    Nullable meter columns are coerced to 0 so the client always receives
    integer values.

    Args:
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``CharactersSummaryResponse`` with one ``CharacterSummaryItem`` per
        active full character, ordered by name ascending.
    """
    stmt = (
        select(Character)
        .where(
            Character.detail_level == "full",
            Character.is_deleted == False,  # noqa: E712
        )
        .order_by(Character.name.asc())
    )
    characters = db.scalars(stmt).all()

    return CharactersSummaryResponse(
        items=[
            CharacterSummaryItem(
                id=c.id,
                name=c.name,
                stress=c.stress or 0,
                free_time=c.free_time or 0,
                plot=c.plot or 0,
                gnosis=c.gnosis or 0,
            )
            for c in characters
        ]
    )


@router.get(
    "/characters/{character_id}",
    response_model=CharacterDetailResponse,
    status_code=200,
    summary="Get character detail",
    description=(
        "Returns the full character record, including soft-deleted characters "
        "(``is_deleted`` will be ``true`` in those cases).  Returns 404 if no "
        "character exists with that ID.  Includes ``locations`` field with "
        "bond-distance location tiers computed from the bond graph."
    ),
)
def get_character(
    character_id: UlidStr,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharacterDetailResponse:
    """Return a single character by ID including bond-distance location tiers.

    For full (PC) characters, also returns all mechanical fields, computed
    values (effective_stress_max, active counts), session history, traits,
    and magic effects.  Simplified characters return only base fields, bonds,
    and locations.

    Args:
        character_id: ULID of the character to retrieve.
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``CharacterDetailResponse`` for the requested character, with
        ``locations`` tiers computed from the bond graph.

    Raises:
        HTTPException(404): If no character exists with ``character_id``.
    """
    character = character_svc.get_character(db, character_id)
    if character is None:
        raise_not_found("Character", character_id)

    bonds_raw = get_bonds_display_for_entity(db, "character", character_id, owned_only=True)
    bonds = BondGroups(
        active=bonds_raw["active"],
        past=bonds_raw["past"],
    )

    locations_raw = get_locations_for_character(db, character_id)
    locations = LocationTiers(
        common=locations_raw["common"],
        familiar=locations_raw["familiar"],
        known=locations_raw["known"],
    )

    base = CharacterResponse.model_validate(character)
    detail_kwargs: dict = {**base.model_dump(), "bonds": bonds, "locations": locations}

    if character.detail_level == "full":
        # --- Traits -----------------------------------------------------------
        trait_slots: list[Slot] = list(
            db.execute(
                select(Slot)
                .where(
                    and_(
                        Slot.owner_type == "character",
                        Slot.owner_id == character_id,
                        Slot.slot_type.in_(["core_trait", "role_trait"]),
                    )
                )
                .order_by(Slot.created_at)
            )
            .scalars()
            .all()
        )

        active_traits: list[CharacterTraitResponse] = []
        past_traits: list[CharacterTraitResponse] = []
        for slot in trait_slots:
            # Resolve name/description from template if linked.
            if slot.template is not None:
                name = slot.template.name
                description = slot.template.description
            else:
                name = slot.name
                description = slot.description
            trait_resp = CharacterTraitResponse(
                id=slot.id,
                slot_type=slot.slot_type,
                name=name,
                description=description,
                charge=slot.charge,
                is_active=slot.is_active,
                template_id=slot.template_id,
                created_at=slot.created_at,
            )
            if slot.is_active:
                active_traits.append(trait_resp)
            else:
                past_traits.append(trait_resp)

        traits = CharacterTraitGroups(active=active_traits, past=past_traits)

        # --- Magic effects ----------------------------------------------------
        effects: list[MagicEffect] = list(
            db.execute(
                select(MagicEffect)
                .where(MagicEffect.character_id == character_id)
                .order_by(MagicEffect.created_at)
            )
            .scalars()
            .all()
        )

        active_effects: list[MagicEffectResponse] = []
        past_effects: list[MagicEffectResponse] = []
        for effect in effects:
            effect_resp = MagicEffectResponse.model_validate(effect)
            if effect.is_active:
                active_effects.append(effect_resp)
            else:
                past_effects.append(effect_resp)

        magic_effects = MagicEffectGroups(active=active_effects, past=past_effects)

        # --- Session history --------------------------------------------------
        session_rows = list(
            db.execute(
                select(SessionParticipant.session_id)
                .where(SessionParticipant.character_id == character_id)
                .order_by(SessionParticipant.session_id)
            ).scalars()
        )
        session_ids = list(session_rows)

        # --- Computed values --------------------------------------------------
        # effective_stress_max: 9 - count of active pc_bond slots where is_trauma=True
        trauma_count = len(
            db.execute(
                select(Slot).where(
                    and_(
                        Slot.owner_type == "character",
                        Slot.owner_id == character_id,
                        Slot.slot_type == "pc_bond",
                        Slot.is_trauma.is_(True),
                        Slot.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        effective_stress_max = 9 - trauma_count

        # active_magic_effects_count: charged + permanent active effects
        active_counted_effects = sum(
            1
            for e in active_effects
            if e.effect_type in ("charged", "permanent")
        )

        # active_trait_count: filled active core_trait + role_trait slots
        active_trait_count = len(active_traits)

        # active_bond_count: active pc_bond slots owned by this character
        active_bond_count = len(
            db.execute(
                select(Slot).where(
                    and_(
                        Slot.owner_type == "character",
                        Slot.owner_id == character_id,
                        Slot.slot_type == "pc_bond",
                        Slot.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

        detail_kwargs.update(
            {
                "stress": character.stress,
                "free_time": character.free_time,
                "plot": character.plot,
                "gnosis": character.gnosis,
                "skills": character.skills,
                "magic_stats": character.magic_stats,
                "last_session_time_now": character.last_session_time_now,
                "effective_stress_max": effective_stress_max,
                "active_magic_effects_count": active_counted_effects,
                "active_trait_count": active_trait_count,
                "active_bond_count": active_bond_count,
                "session_ids": session_ids,
                "traits": traits,
                "magic_effects": magic_effects,
            }
        )

    return CharacterDetailResponse(**detail_kwargs)


@router.patch(
    "/characters/{character_id}",
    response_model=CharacterResponse,
    status_code=200,
    summary="Update a character",
    description=(
        "Partial update for name, description, and notes.  "
        "Omitted fields are unchanged; sending ``null`` clears a nullable field.  "
        "The owning player may edit their own character; the GM may edit any character.  "
        "Mechanical fields (meters, skills, attributes) are changed via GM actions."
    ),
)
def update_character(
    character_id: UlidStr,
    body: UpdateCharacterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CharacterResponse:
    """Apply a partial update to a character.

    Args:
        character_id: ULID of the character to update.
        body: Validated partial update.  Only explicitly provided fields are
            applied (``model_fields_set`` semantics).
        current_user: Authenticated user.  Must be the GM or the character's owner.
        db: Injected SQLAlchemy session.

    Returns:
        ``CharacterResponse`` with updated fields.

    Raises:
        HTTPException(404): If the character does not exist.
        HTTPException(403): If the caller is neither the GM nor the character's owner.
    """
    character = character_svc.get_character(db, character_id)
    if character is None:
        raise_not_found("Character", character_id)

    # Authorization: GM can edit any character; a player can only edit their own.
    if current_user.role != "gm" and current_user.character_id != character_id:
        raise_forbidden("You do not have permission to edit this character.")

    # Build the updates dict from only the fields the caller explicitly provided.
    updates = body.model_dump(exclude_unset=True)

    character = character_svc.update_character(db, character, updates)
    return CharacterResponse.model_validate(character)


@router.delete(
    "/characters/{character_id}",
    status_code=204,
    summary="Soft-delete a character",
    description=(
        "GM only.  Sets ``is_deleted = true`` on the character.  "
        "The character remains accessible via direct GET but is hidden from list results.  "
        "Returns 204 with no body."
    ),
)
def delete_character(
    character_id: UlidStr,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a character.

    Args:
        character_id: ULID of the character to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no character exists with ``character_id``.
    """
    character = character_svc.get_character(db, character_id)
    if character is None:
        raise_not_found("Character", character_id)

    character_svc.delete_character(db, character)
