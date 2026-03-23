"""Route handlers for /api/v1/groups — Group CRUD endpoints.

Provides standard CRUD for the Group resource (organizations, crews, guilds,
and other game-world factions).  All write operations are GM-only; reads are
accessible to any authenticated user.

Endpoints
---------
POST   /groups          — GM only.  Create a group.
GET    /groups          — Authenticated.  List with filters + pagination.
GET    /groups/{id}     — Authenticated.  Group detail (incl. soft-deleted).
PATCH  /groups/{id}     — GM only.  Update name/description/notes.
DELETE /groups/{id}     — GM only.  Soft delete.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.group import Group
from wizards_engine.models.user import User
from wizards_engine.schemas.bond import BondGroups, GroupMemberResponse, TraitDisplayResponse
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.group import (
    CreateGroupRequest,
    GroupDetailResponse,
    GroupResponse,
    UpdateGroupRequest,
)
from wizards_engine.services import group as group_svc
from wizards_engine.services.bond import (
    get_bonds_display_for_entity,
    get_group_members,
    get_traits_for_owner,
)

router = APIRouter()


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=201,
    summary="Create a group",
    description=(
        "GM only.  Creates a new Group with the given name, tier, and optional fields.  "
        "``tier`` is required and must be a non-negative integer.  "
        "Tier changes after creation come via GM actions (Phase 4)."
    ),
)
def create_group(
    body: CreateGroupRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> GroupResponse:
    """Create a new group.

    Args:
        body: Validated request body with name, tier, and optional fields.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``GroupResponse`` for the newly created group (201).
    """
    group = group_svc.create_group(
        db,
        name=body.name,
        tier=body.tier,
        description=body.description,
        notes=body.notes,
    )
    return GroupResponse.model_validate(group)


@router.get(
    "/groups",
    response_model=PaginatedResponse[GroupResponse],
    status_code=200,
    summary="List groups",
    description=(
        "Returns a paginated list of groups.  Soft-deleted groups are "
        "excluded by default.  Supports ``?include_deleted=true`` to reveal "
        "soft-deleted entries.  ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_groups(
    include_deleted: bool = False,
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[GroupResponse]:
    """Return a paginated, filtered list of groups.

    Args:
        include_deleted: When ``true``, include soft-deleted groups.
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``GroupResponse`` objects.
    """
    q = group_svc.list_groups_query(
        db,
        include_deleted=include_deleted,
    )

    page = paginate(db, q, model=Group, after=after, limit=limit)

    return PaginatedResponse[GroupResponse](
        items=[GroupResponse.model_validate(g) for g in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get(
    "/groups/{group_id}",
    response_model=GroupDetailResponse,
    status_code=200,
    summary="Get group detail",
    description=(
        "Returns the full group record, including soft-deleted groups "
        "(``is_deleted`` will be ``true`` in those cases).  Returns 404 if no "
        "group exists with that ID.  Includes ``traits``, ``bonds``, and computed "
        "``members`` list derived from the bond graph."
    ),
)
def get_group(
    group_id: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupDetailResponse:
    """Return a single group by ID with traits, bonds, and derived members.

    Args:
        group_id: ULID of the group to retrieve.
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``GroupDetailResponse`` for the requested group, including active
        ``traits`` (group_trait slots), ``bonds`` (all active + past bonds
        perspective-normalized), and ``members`` (Characters with an active
        bond targeting this group).

    Raises:
        HTTPException(404): If no group exists with ``group_id``.
    """
    group = group_svc.get_group(db, group_id)
    if group is None:
        raise_not_found("Group", group_id)

    trait_slots = get_traits_for_owner(db, "group", group_id, "group_trait")
    traits = [TraitDisplayResponse.model_validate(t) for t in trait_slots]

    bonds_raw = get_bonds_display_for_entity(db, "group", group_id, owned_only=True)
    bonds = BondGroups(active=bonds_raw["active"], past=bonds_raw["past"])

    member_chars = get_group_members(db, group_id)
    members = [GroupMemberResponse.model_validate(c) for c in member_chars]

    base = GroupResponse.model_validate(group)
    return GroupDetailResponse(**base.model_dump(), traits=traits, bonds=bonds, members=members)


@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse,
    status_code=200,
    summary="Update a group",
    description=(
        "GM only.  Partial update for name, description, and notes.  "
        "Omitted fields are unchanged; sending ``null`` clears a nullable field.  "
        "``tier`` is not updatable via PATCH — use GM actions (Phase 4) for tier changes."
    ),
)
def update_group(
    group_id: str,
    body: UpdateGroupRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> GroupResponse:
    """Apply a partial update to a group.

    Args:
        group_id: ULID of the group to update.
        body: Validated partial update.  Only explicitly provided fields are
            applied (``model_fields_set`` semantics).
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``GroupResponse`` with updated fields.

    Raises:
        HTTPException(404): If the group does not exist.
    """
    group = group_svc.get_group(db, group_id)
    if group is None:
        raise_not_found("Group", group_id)

    # Build the updates dict from only the fields the caller explicitly provided.
    updates = body.model_dump(exclude_unset=True)

    group = group_svc.update_group(db, group, updates)
    return GroupResponse.model_validate(group)


@router.delete(
    "/groups/{group_id}",
    status_code=204,
    summary="Soft-delete a group",
    description=(
        "GM only.  Sets ``is_deleted = true`` on the group.  "
        "The group remains accessible via direct GET but is hidden from list results.  "
        "Returns 204 with no body."
    ),
)
def delete_group(
    group_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a group.

    Args:
        group_id: ULID of the group to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no group exists with ``group_id``.
    """
    group = group_svc.get_group(db, group_id)
    if group is None:
        raise_not_found("Group", group_id)

    group_svc.delete_group(db, group)
