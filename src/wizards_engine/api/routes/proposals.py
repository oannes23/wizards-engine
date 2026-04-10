"""Route handlers for /api/v1/proposals — Proposal CRUD + Submission.

Provides the player proposal workflow: submitting, listing, viewing,
editing, and withdrawing proposals.  The GM can view all proposals and
delete non-approved ones.

Endpoints
---------
POST   /proposals                — Authenticated player.  Submit a new proposal.
GET    /proposals                — Authenticated.  List with filters + pagination.
GET    /proposals/{id}           — Authenticated.  Single proposal detail.
PATCH  /proposals/{id}           — Owner or GM.  Update narrative/selections.
DELETE /proposals/{id}           — Owner or GM.  Delete a non-approved proposal.
POST   /proposals/{id}/approve   — GM only.  Approve a pending proposal.
POST   /proposals/{id}/reject    — GM only.  Reject a pending proposal.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from wizards_engine.api.deps import get_current_user, require_gm
from wizards_engine.roles import Role, actor_type_for, has_full_visibility
from wizards_engine.api.pagination import paginate
from wizards_engine.api.responses import raise_forbidden, raise_not_found, validation_error_response
from wizards_engine.api.types import UlidStr
from wizards_engine.db import get_db
from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.proposal import Proposal
from wizards_engine.models.slot import Slot
from wizards_engine.models.story import Story
from wizards_engine.models.user import User
from wizards_engine.schemas.common import PaginatedResponse
from wizards_engine.schemas.proposal import (
    ApproveProposalRequest,
    CalculateEffectResponse,
    CreateProposalRequest,
    ProposalResponse,
    RejectProposalRequest,
    UpdateProposalRequest,
)
from wizards_engine.services import proposal as proposal_svc

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_EDITABLE_STATUSES = frozenset({"pending", "rejected"})


def _resolve_selection_entities(selections: dict, db: Session) -> dict[str, str]:
    """Return a flat {id: name} map for entity IDs referenced in selections."""
    entities: dict[str, str] = {}
    if story_id := selections.get("story_id"):
        s = db.get(Story, story_id)
        if s:
            entities[story_id] = s.name
    if mods := selections.get("modifiers"):
        for key in ("core_trait_id", "role_trait_id", "bond_id"):
            if slot_id := mods.get(key):
                slot = db.get(Slot, slot_id)
                if slot:
                    entities[slot_id] = slot.name
    return entities


def _proposal_response(proposal: Proposal, db: Session) -> ProposalResponse:
    """Build a ProposalResponse with denormalized character_name, clock_name, and selection_entities."""
    resp = ProposalResponse.model_validate(proposal)
    if proposal.character_id:
        char = db.get(Character, proposal.character_id)
        resp.character_name = char.name if char else None
    if proposal.clock_id:
        clk = db.get(Clock, proposal.clock_id)
        resp.clock_name = clk.name if clk else None
    resp.selection_entities = _resolve_selection_entities(proposal.selections, db)
    return resp


def _get_proposal_or_404(db: Session, proposal_id: str) -> Proposal:
    """Return a Proposal by ID or raise 404.

    Args:
        db: Active SQLAlchemy session.
        proposal_id: ULID to look up.

    Returns:
        The matching :class:`~wizards_engine.models.proposal.Proposal`.

    Raises:
        HTTPException(404): If no proposal exists with that ID.
    """
    proposal = proposal_svc.get_proposal(db, proposal_id)
    if proposal is None:
        raise_not_found("Proposal", proposal_id)
    return proposal


def _assert_can_read(proposal: Proposal, current_user: User) -> None:
    """Raise 404 if the player cannot read this proposal.

    GMs and Viewers can read any proposal.  Players can only read proposals
    whose ``character_id`` matches their own ``character_id``.  We raise 404
    (not 403) to avoid leaking existence.

    Args:
        proposal: The proposal to check.
        current_user: The authenticated user.

    Raises:
        HTTPException(404): If the player does not own this proposal.
    """
    if has_full_visibility(current_user):
        return
    if proposal.character_id != current_user.character_id:
        raise_not_found("Proposal", proposal.id)


def _assert_can_mutate(proposal: Proposal, current_user: User) -> None:
    """Raise 403/404 if the user cannot edit or delete this proposal.

    Players can only mutate their own proposals.  GMs can mutate any
    non-approved proposal.  Viewers cannot mutate any proposal.
    Approved proposals cannot be mutated by anyone.

    Args:
        proposal: The proposal to check.
        current_user: The authenticated user.

    Raises:
        HTTPException(403): If the user is a viewer (read-only role).
        HTTPException(404): If the player does not own this proposal.
        HTTPException(409): If the proposal is already approved.
    """
    if current_user.role == Role.VIEWER:
        raise_forbidden("Viewers have read-only access.")

    _assert_can_read(proposal, current_user)

    if proposal.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "proposal_approved",
                    "message": "Approved proposals cannot be modified or deleted.",
                }
            },
        )


# ---------------------------------------------------------------------------
# POST /proposals — submit a new proposal
# ---------------------------------------------------------------------------


@router.post(
    "/proposals",
    response_model=ProposalResponse,
    status_code=201,
    summary="Submit a proposal",
    description=(
        "Authenticated player.  Submits a new action proposal on behalf of "
        "the player's character.  ``character_id`` must match the "
        "authenticated user's own character.  ``action_type`` must be one of "
        "the 10 player-submittable types (``resolve_clock`` and "
        "``resolve_trauma`` are system-only and will be rejected).  "
        "Returns 201 with the created proposal."
    ),
)
def create_proposal(
    body: CreateProposalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """Submit a new player proposal.

    Args:
        body: Validated request body.
        current_user: The authenticated user (any role accepted by the
            dependency, but GM callers are blocked below).
        db: Injected SQLAlchemy session.

    Returns:
        ``ProposalResponse`` for the newly created proposal (201).

    Raises:
        HTTPException(403): If the caller is the GM (proposals are
            player-only).
        HTTPException(422): If ``character_id`` does not belong to the
            authenticated user.
        HTTPException(404): If the referenced character does not exist.
    """
    # Only players may submit proposals.
    if current_user.role != Role.PLAYER:
        raise_forbidden("Only players can submit proposals.")

    # Validate that character_id belongs to this player.
    if current_user.character_id != body.character_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": {
                        "fields": {
                            "character_id": "character_id must belong to the authenticated user"
                        }
                    },
                }
            },
        )

    # Verify the character actually exists.
    character = db.get(Character, body.character_id)
    if character is None:
        raise_not_found("Character", body.character_id)

    proposal = proposal_svc.create_proposal(
        db,
        character_id=body.character_id,
        action_type=body.action_type,
        narrative=body.narrative,
        selections=body.selections,
        actor_id=current_user.id,
    )
    return _proposal_response(proposal, db)


# ---------------------------------------------------------------------------
# POST /proposals/calculate — dry-run calculation
# ---------------------------------------------------------------------------


@router.post(
    "/proposals/calculate",
    response_model=CalculateEffectResponse,
    status_code=200,
    summary="Dry-run proposal calculation",
    description=(
        "Authenticated player.  Computes the ``calculated_effect`` for a "
        "proposed action without creating a proposal record.  Uses the same "
        "request body as ``POST /proposals``.  No side effects."
    ),
)
def calculate_proposal(
    body: CreateProposalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalculateEffectResponse:
    """Compute calculated_effect without persisting a proposal.

    Args:
        body: Validated request body (same shape as create proposal).
        current_user: Authenticated user (GM blocked).
        db: Injected SQLAlchemy session.

    Returns:
        ``CalculateEffectResponse`` wrapping the computed effect dict.

    Raises:
        HTTPException(403): If the caller is the GM.
        HTTPException(422): If ``character_id`` does not belong to the user.
        HTTPException(404): If the character does not exist.
    """
    # Only players may use the calculate endpoint.
    if current_user.role != Role.PLAYER:
        raise_forbidden("Only players can use the proposal calculate endpoint.")

    if current_user.character_id != body.character_id:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed",
                    "details": {
                        "fields": {
                            "character_id": "character_id must belong to the authenticated user"
                        }
                    },
                }
            },
        )

    character = db.get(Character, body.character_id)
    if character is None:
        raise_not_found("Character", body.character_id)

    calculated_effect = proposal_svc.calculate_effect(
        db,
        character_id=body.character_id,
        action_type=body.action_type,
        selections=body.selections,
    )
    return CalculateEffectResponse(calculated_effect=calculated_effect)


# ---------------------------------------------------------------------------
# GET /proposals — paginated list
# ---------------------------------------------------------------------------


@router.get(
    "/proposals",
    response_model=PaginatedResponse[ProposalResponse],
    status_code=200,
    summary="List proposals",
    description=(
        "Returns a paginated list of proposals.  Players see only their own "
        "proposals; the GM sees all proposals.  Supports optional filters: "
        "``status`` (pending|approved|rejected), ``character_id``, "
        "``action_type``.  "
        "ULID cursor pagination via ``?after=<ulid>&limit=N``."
    ),
)
def list_proposals(
    status: str | None = None,
    character_id: str | None = None,
    action_type: str | None = None,
    after: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProposalResponse]:
    """Return a paginated, filtered list of proposals.

    Args:
        status: Optional filter — ``"pending"``, ``"approved"``, or
            ``"rejected"``.
        character_id: Optional filter — only proposals for this character ULID.
            For players, this is ignored in favour of their own character.
        action_type: Optional filter — exact match on action_type.
        after: ULID cursor for pagination (return items older than this ID).
        limit: Page size (default 50, max 100).
        current_user: Authenticated user (any role).
        db: Injected SQLAlchemy session.

    Returns:
        ``PaginatedResponse`` wrapping a list of ``ProposalResponse`` objects.
    """
    if status is not None and status not in ("pending", "approved", "rejected"):
        return validation_error_response(
            {"status": "must be 'pending', 'approved', or 'rejected'"}
        )

    # Players are restricted to their own proposals.
    owner_character_id: str | None = None
    if not has_full_visibility(current_user):
        owner_character_id = current_user.character_id

    q = proposal_svc.list_proposals_query(
        db,
        character_id=character_id,
        status=status,
        action_type=action_type,
        owner_character_id=owner_character_id,
    )

    page = paginate(db, q, model=Proposal, after=after, limit=limit)

    return PaginatedResponse[ProposalResponse](
        items=[_proposal_response(p, db) for p in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


# ---------------------------------------------------------------------------
# GET /proposals/{id} — single proposal detail
# ---------------------------------------------------------------------------


@router.get(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
    status_code=200,
    summary="Get proposal detail",
    description=(
        "Returns the full proposal record.  Players can only view their own "
        "proposals; the GM can view any.  Returns 404 if not found or if a "
        "player attempts to access another player's proposal."
    ),
)
def get_proposal(
    proposal_id: UlidStr,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """Return a single proposal by ID.

    Args:
        proposal_id: ULID of the proposal to retrieve.
        current_user: Authenticated user.
        db: Injected SQLAlchemy session.

    Returns:
        ``ProposalResponse`` for the requested proposal.

    Raises:
        HTTPException(404): If the proposal does not exist or is not
            accessible to the caller.
    """
    proposal = _get_proposal_or_404(db, proposal_id)
    _assert_can_read(proposal, current_user)
    return _proposal_response(proposal, db)


# ---------------------------------------------------------------------------
# PATCH /proposals/{id} — update narrative/selections
# ---------------------------------------------------------------------------


@router.patch(
    "/proposals/{proposal_id}",
    response_model=ProposalResponse,
    status_code=200,
    summary="Update a proposal",
    description=(
        "Authenticated player (owner) or GM.  Only allowed when status is "
        "``pending`` or ``rejected``.  Can update ``narrative`` and/or "
        "``selections``.  If the proposal was ``rejected``, its status "
        "reverts to ``pending`` and a ``proposal.revised`` event is "
        "created.  Returns 409 if the proposal is already ``approved``."
    ),
)
def update_proposal(
    proposal_id: UlidStr,
    body: UpdateProposalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """Apply a partial update to a proposal.

    Args:
        proposal_id: ULID of the proposal to update.
        body: Validated partial update.
        current_user: Authenticated user.  Must be the GM or the proposal's
            owning player.
        db: Injected SQLAlchemy session.

    Returns:
        ``ProposalResponse`` with updated fields.

    Raises:
        HTTPException(404): If the proposal does not exist or is not
            accessible to the caller.
        HTTPException(409): If the proposal is already approved.
    """
    proposal = _get_proposal_or_404(db, proposal_id)
    _assert_can_mutate(proposal, current_user)

    actor_type = actor_type_for(current_user)

    proposal = proposal_svc.update_proposal(
        db,
        proposal,
        narrative=body.narrative,
        selections=body.selections,
        actor_id=current_user.id,
        actor_type=actor_type,
    )
    return _proposal_response(proposal, db)


# ---------------------------------------------------------------------------
# DELETE /proposals/{id} — hard delete
# ---------------------------------------------------------------------------


@router.delete(
    "/proposals/{proposal_id}",
    status_code=204,
    summary="Delete a proposal",
    description=(
        "Authenticated player (owner) or GM.  Hard-deletes the proposal.  "
        "Only allowed when status is ``pending`` or ``rejected``.  "
        "Returns 409 if the proposal is already ``approved``.  "
        "Returns 204 with no body on success."
    ),
)
def delete_proposal(
    proposal_id: UlidStr,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Hard-delete a proposal.

    Args:
        proposal_id: ULID of the proposal to delete.
        current_user: Authenticated user.  Must be the GM or the proposal's
            owning player.
        db: Injected SQLAlchemy session.

    Returns:
        ``None`` — FastAPI sends 204 No Content.

    Raises:
        HTTPException(404): If the proposal does not exist or is not
            accessible to the caller.
        HTTPException(409): If the proposal is already approved.
    """
    proposal = _get_proposal_or_404(db, proposal_id)
    _assert_can_mutate(proposal, current_user)
    proposal_svc.delete_proposal(db, proposal)


# ---------------------------------------------------------------------------
# POST /proposals/{id}/approve — GM approval
# ---------------------------------------------------------------------------


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ProposalResponse,
    status_code=200,
    summary="Approve a proposal",
    description=(
        "GM only.  Approves a ``pending`` proposal, applies resource deductions, "
        "and creates a ``proposal.approved`` event.  Optionally accepts a GM "
        "narrative override, field overrides for the calculated effect, and a "
        "rider event.  Returns 409 if the proposal is not ``pending`` or if "
        "resources are insufficient (use ``gm_overrides.force = true`` to "
        "bypass the resource check)."
    ),
)
def approve_proposal(
    proposal_id: UlidStr,
    body: ApproveProposalRequest,
    current_user: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """Approve a pending proposal as the GM.

    Args:
        proposal_id: ULID of the proposal to approve.
        body: Validated approval payload.
        current_user: The authenticated GM user (enforced by ``require_gm``).
        db: Injected SQLAlchemy session.

    Returns:
        ``ProposalResponse`` with updated status ``"approved"`` and populated
        ``event_id``.

    Raises:
        HTTPException(404): If the proposal does not exist.
        HTTPException(409): If the proposal is not ``pending``.
        HTTPException(409): If resources are insufficient and ``force`` is
            not set.
    """
    proposal = _get_proposal_or_404(db, proposal_id)

    rider_payload = (
        body.rider_event.model_dump(exclude_none=True) if body.rider_event else None
    )

    proposal = proposal_svc.approve_proposal(
        db,
        proposal,
        actor_id=current_user.id,
        narrative=body.narrative,
        gm_overrides=body.gm_overrides,
        rider_event_payload=rider_payload,
    )
    return _proposal_response(proposal, db)


# ---------------------------------------------------------------------------
# POST /proposals/{id}/reject — GM rejection
# ---------------------------------------------------------------------------


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ProposalResponse,
    status_code=200,
    summary="Reject a proposal",
    description=(
        "GM only.  Rejects a ``pending`` proposal.  Optionally accepts a "
        "rejection note stored in ``gm_notes``.  Creates a "
        "``proposal.rejected`` event with ``private`` visibility.  "
        "Returns 409 if the proposal is not ``pending``."
    ),
)
def reject_proposal(
    proposal_id: UlidStr,
    body: RejectProposalRequest,
    current_user: User = Depends(require_gm),
    db: Session = Depends(get_db),
) -> ProposalResponse:
    """Reject a pending proposal as the GM.

    Args:
        proposal_id: ULID of the proposal to reject.
        body: Validated rejection payload.
        current_user: The authenticated GM user (enforced by ``require_gm``).
        db: Injected SQLAlchemy session.

    Returns:
        ``ProposalResponse`` with updated status ``"rejected"`` and
        ``gm_notes`` populated if a rejection note was supplied.

    Raises:
        HTTPException(404): If the proposal does not exist.
        HTTPException(409): If the proposal is not ``pending``.
    """
    proposal = _get_proposal_or_404(db, proposal_id)

    proposal = proposal_svc.reject_proposal(
        db,
        proposal,
        actor_id=current_user.id,
        rejection_note=body.rejection_note,
    )
    return _proposal_response(proposal, db)
