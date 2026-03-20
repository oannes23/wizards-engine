"""CRUD operations for proposals: create, get, list, update, delete."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.proposal import Proposal
from wizards_engine.services.event import create_event

from .calculators import (
    calculate_charge_magic,
    calculate_new_bond,
    calculate_new_trait,
    calculate_regain_gnosis,
    calculate_rest,
    calculate_use_magic,
    calculate_use_skill,
    calculate_work_on_project,
)
from .constants import DOWNTIME_ACTION_TYPES


def create_proposal(
    db: Session,
    *,
    character_id: str,
    action_type: str,
    narrative: str | None,
    selections: dict[str, Any],
    actor_id: str,
) -> Proposal:
    """Create a new player-submitted proposal in ``pending`` status.

    For ``use_skill`` proposals, computes and stores the ``calculated_effect``
    immediately.  For all other action types, ``calculated_effect`` is set to
    ``{}`` (deferred to later stories).

    Args:
        db: Active SQLAlchemy session.
        character_id: ULID of the submitting character.
        action_type: One of the 10 player-submittable action types.
        narrative: Player-written description of the intended action.
        selections: Type-specific input dict.
        actor_id: ULID of the authenticated user (for event creation).

    Returns:
        The newly created and flushed Proposal instance.
    """
    calculated_effect: dict[str, Any] = {}
    if action_type == "use_skill":
        calculated_effect = calculate_use_skill(
            db, character_id=character_id, selections=selections
        )
    elif action_type == "use_magic":
        calculated_effect = calculate_use_magic(
            db, character_id=character_id, selections=selections
        )
    elif action_type == "charge_magic":
        calculated_effect = calculate_charge_magic(
            db, character_id=character_id, selections=selections
        )
    elif action_type in DOWNTIME_ACTION_TYPES:
        character: Character | None = db.get(Character, character_id)
        if character is not None:
            if action_type == "regain_gnosis":
                calculated_effect = calculate_regain_gnosis(db, character, selections)
            elif action_type == "work_on_project":
                calculated_effect = calculate_work_on_project(db, character, selections)
            elif action_type == "rest":
                calculated_effect = calculate_rest(db, character, selections)
            elif action_type == "new_trait":
                calculated_effect = calculate_new_trait(db, character, selections)
            elif action_type == "new_bond":
                calculated_effect = calculate_new_bond(db, character, selections)

    proposal = Proposal(
        character_id=character_id,
        action_type=action_type,
        origin="player",
        narrative=narrative,
        selections=selections,
        calculated_effect=calculated_effect,
        status="pending",
    )
    db.add(proposal)
    db.flush()
    db.refresh(proposal)
    return proposal


def get_proposal(db: Session, proposal_id: str) -> Proposal | None:
    """Retrieve a single proposal by ULID, or ``None`` if not found."""
    return db.get(Proposal, proposal_id)


def list_proposals_query(
    db: Session,
    *,
    character_id: str | None = None,
    status: str | None = None,
    action_type: str | None = None,
    owner_character_id: str | None = None,
):
    """Build a SQLAlchemy select query for proposals with optional filters.

    Does not execute the query.  The caller is responsible for applying
    pagination and executing.
    """
    q = select(Proposal)

    # Ownership restriction: players can only see their own proposals.
    if owner_character_id is not None:
        q = q.where(Proposal.character_id == owner_character_id)
    # Explicit character_id filter: only applied when there is no ownership
    # restriction (i.e., GM callers).
    elif character_id is not None:
        q = q.where(Proposal.character_id == character_id)

    if status is not None:
        q = q.where(Proposal.status == status)

    if action_type is not None:
        q = q.where(Proposal.action_type == action_type)

    return q


def update_proposal(
    db: Session,
    proposal: Proposal,
    *,
    narrative: str | None = None,
    selections: dict[str, Any] | None = None,
    actor_id: str,
    actor_type: str,
) -> Proposal:
    """Apply a partial update to a proposal.

    If the proposal was previously ``rejected``, changes its status back to
    ``pending`` and creates a ``proposal.revised`` event.
    """
    was_rejected = proposal.status == "rejected"

    if narrative is not None:
        proposal.narrative = narrative

    if selections is not None:
        proposal.selections = selections

    # Recalculate effect whenever selections change (or on revision).
    if proposal.action_type == "use_skill" and (
        selections is not None or was_rejected
    ):
        proposal.calculated_effect = calculate_use_skill(
            db,
            character_id=proposal.character_id,
            selections=proposal.selections,
        )
    elif proposal.action_type == "use_magic" and (
        selections is not None or was_rejected
    ):
        proposal.calculated_effect = calculate_use_magic(
            db,
            character_id=proposal.character_id,
            selections=proposal.selections,
        )
    elif proposal.action_type == "charge_magic" and (
        selections is not None or was_rejected
    ):
        proposal.calculated_effect = calculate_charge_magic(
            db,
            character_id=proposal.character_id,
            selections=proposal.selections,
        )
    elif proposal.action_type in DOWNTIME_ACTION_TYPES and (
        selections is not None or was_rejected
    ):
        dt_character: Character | None = db.get(Character, proposal.character_id)
        if dt_character is not None:
            if proposal.action_type == "regain_gnosis":
                proposal.calculated_effect = calculate_regain_gnosis(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "work_on_project":
                proposal.calculated_effect = calculate_work_on_project(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "rest":
                proposal.calculated_effect = calculate_rest(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "new_trait":
                proposal.calculated_effect = calculate_new_trait(
                    db, dt_character, proposal.selections
                )
            elif proposal.action_type == "new_bond":
                proposal.calculated_effect = calculate_new_bond(
                    db, dt_character, proposal.selections
                )

    if was_rejected:
        proposal.status = "pending"

    db.flush()

    if was_rejected:
        revised_targets: list[dict] = []
        if proposal.character_id is not None:
            revised_targets = [
                {
                    "target_type": "character",
                    "target_id": proposal.character_id,
                    "is_primary": True,
                }
            ]
        create_event(
            db,
            type="proposal.revised",
            actor_type=actor_type,
            actor_id=actor_id,
            visibility="private",
            proposal_id=proposal.id,
            targets=revised_targets,
        )

    db.refresh(proposal)
    return proposal


def delete_proposal(db: Session, proposal: Proposal) -> None:
    """Hard-delete a proposal from the database."""
    db.delete(proposal)
    db.flush()
