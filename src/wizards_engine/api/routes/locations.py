"""Route handlers for /api/v1/locations — Location CRUD endpoints.

Provides standard CRUD for the Location resource.  Locations form a nestable
hierarchy via ``parent_id``.  Parent changes are deferred to GM actions (Phase 4).

Endpoints
---------
POST   /locations          — GM only.  Create a location.
GET    /locations          — Authenticated.  List with filters + pagination.
GET    /locations/{id}     — Authenticated.  Location detail (incl. soft-deleted).
PATCH  /locations/{id}     — GM only.  Update name/description/notes.
DELETE /locations/{id}     — GM only.  Soft delete.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_not_found
from wizards_engine.db import get_db
from wizards_engine.models.location import Location
from wizards_engine.models.user import User
from wizards_engine.schemas.bond import BondGroups, TraitDisplayResponse
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.location import (
    CreateLocationRequest,
    LocationDetailResponse,
    LocationResponse,
    PresenceTiers,
    UpdateLocationRequest,
)
from wizards_engine.services import location as location_svc
from wizards_engine.services.bond import get_bonds_display_for_entity, get_traits_for_owner
from wizards_engine.services.presence import get_presence_for_location

router = APIRouter()


@router.post(
    "/locations",
    response_model=LocationResponse,
    status_code=201,
    summary="Create a location",
    description=(
        "GM only.  Creates a new location.  "
        "``parent_id`` is optional — when provided it must reference an existing "
        "location and establishes the hierarchy.  ``parent_id`` changes after "
        "creation go through GM actions (Phase 4)."
    ),
)
def create_location(
    body: CreateLocationRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> LocationResponse:
    """Create a new location.

    Args:
        body: Validated request body with name and optional fields.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``LocationResponse`` for the newly created location (201).

    Raises:
        HTTPException(422): If ``parent_id`` is provided but does not
            reference an existing location.
    """
    if body.parent_id is not None:
        parent = location_svc.get_location(db, body.parent_id)
        if parent is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "validation_error",
                        "message": "Validation failed",
                        "details": {
                            "fields": {
                                "parent_id": f"Location '{body.parent_id}' does not exist."
                            }
                        },
                    }
                },
            )

    location = location_svc.create_location(
        db,
        name=body.name,
        description=body.description,
        parent_id=body.parent_id,
        notes=body.notes,
    )
    return LocationResponse.model_validate(location)


@router.get(
    "/locations",
    response_model=PaginatedResponse[LocationResponse],
    status_code=200,
    summary="List locations",
    description=(
        "Returns a paginated list of locations.  Soft-deleted locations are "
        "excluded by default.  Supports filtering by parent (direct children only) "
        "and include_deleted.  "
        "ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_locations(
    parent: str | None = None,
    include_deleted: bool = False,
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[LocationResponse]:
    """Return a paginated, filtered list of locations.

    Args:
        parent: Optional ULID filter — returns only direct children of that
            location (not recursive).
        include_deleted: When ``true``, include soft-deleted locations.
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``LocationResponse`` objects.
    """
    q = location_svc.list_locations_query(
        db,
        parent_id=parent,
        include_deleted=include_deleted,
    )

    page = paginate(db, q, model=Location, after=after, limit=limit)

    return PaginatedResponse[LocationResponse](
        items=[LocationResponse.model_validate(loc) for loc in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get(
    "/locations/{location_id}",
    response_model=LocationDetailResponse,
    status_code=200,
    summary="Get location detail",
    description=(
        "Returns the full location record, including soft-deleted locations "
        "(``is_deleted`` will be ``true`` in those cases).  Returns 404 if no "
        "location exists with that ID.  Includes ``presence`` field with "
        "bond-distance character tiers computed from the bond graph."
    ),
)
def get_location(
    location_id: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LocationDetailResponse:
    """Return a single location by ID including bond-distance presence tiers.

    Args:
        location_id: ULID of the location to retrieve.
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``LocationDetailResponse`` for the requested location, with
        ``presence`` tiers computed from the bond graph.

    Raises:
        HTTPException(404): If no location exists with ``location_id``.
    """
    location = location_svc.get_location(db, location_id)
    if location is None:
        raise_not_found("Location", location_id)

    trait_slots = get_traits_for_owner(db, "location", location_id, "feature_trait")
    traits = [TraitDisplayResponse.model_validate(t) for t in trait_slots]

    bonds_raw = get_bonds_display_for_entity(db, "location", location_id, owned_only=True)
    bonds = BondGroups(active=bonds_raw["active"], past=bonds_raw["past"])

    presence_raw = get_presence_for_location(db, location_id)
    presence = PresenceTiers(
        common=presence_raw["common"],
        familiar=presence_raw["familiar"],
        known=presence_raw["known"],
    )

    base = LocationResponse.model_validate(location)
    return LocationDetailResponse(**base.model_dump(), traits=traits, bonds=bonds, presence=presence)


@router.patch(
    "/locations/{location_id}",
    response_model=LocationResponse,
    status_code=200,
    summary="Update a location",
    description=(
        "GM only.  Partial update for name, description, and notes.  "
        "Omitted fields are unchanged; sending ``null`` clears a nullable field.  "
        "``parent_id`` changes go through GM actions (Phase 4)."
    ),
)
def update_location(
    location_id: str,
    body: UpdateLocationRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> LocationResponse:
    """Apply a partial update to a location.

    Args:
        location_id: ULID of the location to update.
        body: Validated partial update.  Only explicitly provided fields are
            applied (``model_fields_set`` semantics).
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``LocationResponse`` with updated fields.

    Raises:
        HTTPException(404): If the location does not exist.
    """
    location = location_svc.get_location(db, location_id)
    if location is None:
        raise_not_found("Location", location_id)

    # Build the updates dict from only the fields the caller explicitly provided.
    updates = body.model_dump(exclude_unset=True)

    location = location_svc.update_location(db, location, updates)
    return LocationResponse.model_validate(location)


@router.delete(
    "/locations/{location_id}",
    status_code=204,
    summary="Soft-delete a location",
    description=(
        "GM only.  Sets ``is_deleted = true`` on the location.  "
        "The location remains accessible via direct GET but is hidden from list results.  "
        "Returns 204 with no body."
    ),
)
def delete_location(
    location_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a location.

    Args:
        location_id: ULID of the location to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no location exists with ``location_id``.
    """
    location = location_svc.get_location(db, location_id)
    if location is None:
        raise_not_found("Location", location_id)

    location_svc.delete_location(db, location)
