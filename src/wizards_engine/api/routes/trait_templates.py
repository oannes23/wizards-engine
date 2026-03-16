"""Route handlers for /api/v1/trait-templates — Trait Template CRUD endpoints.

Provides standard CRUD for the TraitTemplate resource.  All write operations
are GM-only; reads are accessible to any authenticated user.

Trait Templates are the definition layer for PC Core and Role traits.  Multiple
characters can share the same template.  Editing a template's name or
description propagates by reference — character trait instances store a
``template_id`` and the API reads ``template.name`` at response time.

Endpoints
---------
POST   /trait-templates          — GM only.  Create a template.
GET    /trait-templates          — Authenticated.  List with filters + pagination.
GET    /trait-templates/{id}     — Authenticated.  Detail (incl. soft-deleted).
PATCH  /trait-templates/{id}     — GM only.  Update name/description only.
DELETE /trait-templates/{id}     — GM only.  Soft delete.
"""

from fastapi import APIRouter, Depends, HTTPException

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import error_response
from wizards_engine.db import get_db
from wizards_engine.models.slot import TraitTemplate
from wizards_engine.models.user import User
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.trait_template import (
    CreateTraitTemplateRequest,
    TraitTemplateResponse,
    UpdateTraitTemplateRequest,
)
from wizards_engine.services import trait_template as trait_template_svc

from sqlalchemy.orm import Session

router = APIRouter()


@router.post(
    "/trait-templates",
    response_model=TraitTemplateResponse,
    status_code=201,
    summary="Create a trait template",
    description=(
        "GM only.  Creates a new Trait Template in the catalog.  "
        "``type`` must be ``'core'`` or ``'role'`` and is immutable after creation.  "
        "Templates are shared — multiple characters can reference the same template.  "
        "Editing a template's name or description propagates to all referencing characters."
    ),
)
def create_trait_template(
    body: CreateTraitTemplateRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> TraitTemplateResponse:
    """Create a new Trait Template in the catalog.

    Args:
        body: Validated request body with name, description, and type.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``TraitTemplateResponse`` for the newly created template (201).
    """
    template = trait_template_svc.create_trait_template(
        db,
        name=body.name,
        description=body.description,
        template_type=body.type,
    )
    return TraitTemplateResponse.model_validate(template)


@router.get(
    "/trait-templates",
    response_model=PaginatedResponse[TraitTemplateResponse],
    status_code=200,
    summary="List trait templates",
    description=(
        "Returns a paginated list of Trait Templates.  Soft-deleted templates are "
        "excluded by default.  Supports filtering by ``?type=core|role`` and "
        "``?include_deleted=true``.  ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_trait_templates(
    type: str | None = None,
    include_deleted: bool = False,
    after: str | None = None,
    limit: int = 50,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[TraitTemplateResponse]:
    """Return a paginated, filtered list of Trait Templates.

    Args:
        type: Optional filter — ``"core"`` or ``"role"``.
        include_deleted: When ``true``, include soft-deleted templates.
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``TraitTemplateResponse`` objects.
    """
    if type is not None and type not in ("core", "role"):
        return error_response(
            status_code=422,
            code="validation_error",
            message="Validation failed",
            details={"fields": {"type": "must be 'core' or 'role'"}},
        )

    q = trait_template_svc.list_trait_templates_query(
        db,
        template_type=type,
        include_deleted=include_deleted,
    )

    page = paginate(db, q, model=TraitTemplate, after=after, limit=limit)

    return PaginatedResponse[TraitTemplateResponse](
        items=[TraitTemplateResponse.model_validate(t) for t in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get(
    "/trait-templates/{template_id}",
    response_model=TraitTemplateResponse,
    status_code=200,
    summary="Get trait template detail",
    description=(
        "Returns the full template record.  Resolves even when the template is "
        "soft-deleted (``is_deleted`` will be ``true`` in those cases) — this is "
        "required for trait instance display on character sheets.  "
        "Returns 404 if no template exists with that ID."
    ),
)
def get_trait_template(
    template_id: str,
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TraitTemplateResponse:
    """Return a single Trait Template by ID including soft-deleted ones.

    Args:
        template_id: ULID of the template to retrieve.
        _current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``TraitTemplateResponse`` for the requested template.

    Raises:
        HTTPException(404): If no template exists with ``template_id``.
    """
    template = trait_template_svc.get_trait_template(db, template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Trait template '{template_id}' not found.",
                }
            },
        )
    return TraitTemplateResponse.model_validate(template)


@router.patch(
    "/trait-templates/{template_id}",
    response_model=TraitTemplateResponse,
    status_code=200,
    summary="Update a trait template",
    description=(
        "GM only.  Partial update for ``name`` and ``description`` only.  "
        "``type`` is immutable — attempting to include ``type`` in the body "
        "returns 422.  Omitted fields are unchanged.  "
        "Name and description changes propagate by reference to all character "
        "trait instances using this template."
    ),
)
def update_trait_template(
    template_id: str,
    body: UpdateTraitTemplateRequest,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> TraitTemplateResponse:
    """Apply a partial update to a Trait Template.

    Args:
        template_id: ULID of the template to update.
        body: Validated partial update.  Only ``name`` and ``description``
            are accepted (``model_fields_set`` semantics).
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``TraitTemplateResponse`` with updated fields.

    Raises:
        HTTPException(404): If the template does not exist.
        HTTPException(422): If the request body contains ``type``.
    """
    template = trait_template_svc.get_trait_template(db, template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Trait template '{template_id}' not found.",
                }
            },
        )

    # Build the updates dict from only the fields the caller explicitly provided.
    updates = body.model_dump(exclude_unset=True)

    template = trait_template_svc.update_trait_template(db, template, updates)
    return TraitTemplateResponse.model_validate(template)


@router.delete(
    "/trait-templates/{template_id}",
    status_code=204,
    summary="Soft-delete a trait template",
    description=(
        "GM only.  Sets ``is_deleted = true`` on the template.  "
        "Existing trait instances that reference this template are NOT affected — "
        "they keep their ``template_id`` and remain fully functional.  "
        "The template is hidden from the list endpoint but remains resolvable by "
        "direct GET for instance display.  Returns 204 with no body.  "
        "Deleting an already-deleted template is idempotent (returns 204)."
    ),
)
def delete_trait_template(
    template_id: str,
    _gm: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a Trait Template.

    Idempotent — deleting an already-deleted template succeeds silently.

    Args:
        template_id: ULID of the template to delete.
        _gm: The authenticated GM (injected; ensures GM-only access).
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If no template exists with ``template_id``.
    """
    template = trait_template_svc.get_trait_template(db, template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Trait template '{template_id}' not found.",
                }
            },
        )

    # Idempotent — already deleted templates are a no-op.
    if not template.is_deleted:
        trait_template_svc.delete_trait_template(db, template)
