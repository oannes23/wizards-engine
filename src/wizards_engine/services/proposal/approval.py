"""Proposal approval and rejection logic."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.proposal import Proposal
from wizards_engine.services.event import create_event
from wizards_engine.services.exceptions import InsufficientResources, ProposalNotPending
from wizards_engine.services.shared import count_trauma_bonds, has_pending_resolve_trauma

from .apply import APPLY_HANDLERS, check_affordability, merge_overrides
from .constants import STRESS_MAX


def approve_proposal(
    db: Session,
    proposal: Proposal,
    *,
    actor_id: str,
    narrative: str | None = None,
    gm_overrides: dict[str, Any] | None = None,
    rider_event_payload: dict[str, Any] | None = None,
) -> Proposal:
    """Approve a pending proposal, deduct resources, and create events.

    Validates affordability at approval time.  If resources are insufficient
    the caller must pass ``gm_overrides={"force": True}`` to bypass.

    Args:
        db: Active SQLAlchemy session.
        proposal: The Proposal to approve.  Must have ``status = "pending"``.
        actor_id: ULID of the GM user performing the approval.
        narrative: GM narrative override for the event.
        gm_overrides: Optional dict of fields that replace corresponding
            entries in ``calculated_effect``.
        rider_event_payload: Optional dict for a rider event.

    Returns:
        The updated and refreshed Proposal (status = ``"approved"``).

    Raises:
        ProposalNotPending: If the proposal is not ``pending``.
        InsufficientResources: If resources are insufficient and ``force`` is
            not set in ``gm_overrides``.
    """
    if proposal.status != "pending":
        raise ProposalNotPending(proposal.id)

    gm_overrides = gm_overrides or {}
    force: bool = bool(gm_overrides.get("force", False))

    # Compute the effective effect: calculated_effect + gm_overrides.
    calculated_effect: dict[str, Any] = proposal.calculated_effect or {}
    effective_effect = merge_overrides(calculated_effect, gm_overrides)

    # Re-validate affordability (resources may have changed since submission).
    if not force and proposal.character_id is not None:
        character: Character | None = db.get(Character, proposal.character_id)
        if character is not None:
            insufficient = check_affordability(db, character, effective_effect)
            if insufficient:
                raise InsufficientResources(
                    "insufficient_resources",
                    "Character no longer has sufficient resources.",
                    insufficient,
                )

    # Apply action-type-specific resource deduction.
    changes: dict[str, Any] = {}
    if proposal.character_id is not None:
        character = db.get(Character, proposal.character_id)
        if character is not None:
            handler = APPLY_HANDLERS.get(proposal.action_type)
            if handler is not None:
                changes = handler(db, character, effective_effect, gm_overrides)

    # Persist gm_overrides on the proposal (store the raw overrides as supplied).
    proposal.gm_overrides = gm_overrides if gm_overrides else None

    # Determine event narrative.
    event_narrative = narrative if narrative is not None else proposal.narrative

    # Build targets for the approval event.
    targets: list[dict[str, Any]] = []
    if proposal.character_id is not None:
        targets.append(
            {
                "target_type": "character",
                "target_id": proposal.character_id,
                "is_primary": True,
            }
        )

    # Create the approval event.
    approval_event = create_event(
        db,
        type="proposal.approved",
        actor_type="gm",
        actor_id=actor_id,
        changes=changes,
        narrative=event_narrative,
        visibility="bonded",
        targets=targets,
        proposal_id=proposal.id,
    )

    # Magic action: stress boundary check (auto-generate resolve_trauma).
    # Must run after approval event creation so we have a parent_event_id.
    if proposal.action_type in ("use_magic", "charge_magic") and proposal.character_id is not None:
        character = db.get(Character, proposal.character_id)
        if character is not None and character.stress is not None:
            _stress_change_key = f"character.{character.id}.stress"
            if _stress_change_key in changes:
                trauma_count = count_trauma_bonds(db, character.id)
                effective_stress_max = STRESS_MAX - trauma_count
                if character.stress >= effective_stress_max and not has_pending_resolve_trauma(
                    db, character.id
                ):
                    trauma_proposal = Proposal(
                        character_id=character.id,
                        action_type="resolve_trauma",
                        origin="system",
                        narrative="",
                        selections={},
                        status="pending",
                    )
                    db.add(trauma_proposal)
                    db.flush()
                    create_event(
                        db,
                        type="character.resolve_trauma_generated",
                        actor_type="system",
                        actor_id=None,
                        changes={},
                        visibility="silent",
                        parent_event_id=approval_event.id,
                        targets=[
                            {
                                "target_type": "character",
                                "target_id": character.id,
                                "is_primary": True,
                            }
                        ],
                        metadata={"proposal_id": trauma_proposal.id},
                    )

    # Create rider event if provided.
    rider_event_id: str | None = None
    if rider_event_payload is not None:
        rider_event = create_event(
            db,
            type=rider_event_payload.get("type", "rider.event"),
            actor_type="gm",
            actor_id=actor_id,
            changes=rider_event_payload.get("changes") or {},
            narrative=rider_event_payload.get("narrative"),
            visibility=rider_event_payload.get("visibility", "bonded"),
            targets=rider_event_payload.get("targets") or [],
            parent_event_id=approval_event.id,
            metadata=rider_event_payload.get("metadata"),
        )
        rider_event_id = rider_event.id

    # Update proposal state.
    proposal.status = "approved"
    proposal.event_id = approval_event.id
    if rider_event_id is not None:
        proposal.rider_event_id = rider_event_id

    db.flush()
    db.refresh(proposal)
    return proposal


def reject_proposal(
    db: Session,
    proposal: Proposal,
    *,
    actor_id: str,
    rejection_note: str | None = None,
) -> Proposal:
    """Reject a pending proposal with an optional rejection note.

    Sets the proposal's status to ``"rejected"`` and records the note in
    ``gm_notes``.  Creates a ``proposal.rejected`` event with ``private``
    visibility.

    Raises:
        ProposalNotPending: If the proposal is not ``pending``.
    """
    if proposal.status != "pending":
        raise ProposalNotPending(proposal.id)

    proposal.status = "rejected"
    if rejection_note is not None:
        proposal.gm_notes = rejection_note

    db.flush()

    # Build targets.
    targets: list[dict[str, Any]] = []
    if proposal.character_id is not None:
        targets.append(
            {
                "target_type": "character",
                "target_id": proposal.character_id,
                "is_primary": True,
            }
        )

    create_event(
        db,
        type="proposal.rejected",
        actor_type="gm",
        actor_id=actor_id,
        visibility="private",
        narrative=rejection_note,
        targets=targets,
        proposal_id=proposal.id,
    )

    db.refresh(proposal)
    return proposal
