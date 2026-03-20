"""Add CHECK constraints to enum columns and index on events.created_at

Adds database-level CHECK constraints on all enum-valued string columns and
a performance index on events.created_at for timeline queries.

SQLite does not support adding constraints with a plain ALTER TABLE, so each
table is recreated via Alembic's batch_alter_table (copy-alter strategy).

Revision ID: 02a420cce9eb
Revises: a7c3e1f09b22
Create Date: 2026-03-19 19:43:14.860547

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '02a420cce9eb'
down_revision: Union[str, Sequence[str], None] = 'a7c3e1f09b22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Enum value sets (kept as module-level constants for readability)
# ---------------------------------------------------------------------------

_PROPOSAL_STATUSES = "('pending', 'approved', 'rejected')"
_PROPOSAL_ACTION_TYPES = (
    "('use_skill', 'use_magic', 'charge_magic', 'regain_gnosis', "
    "'work_on_project', 'rest', 'new_trait', 'new_bond', "
    "'resolve_clock', 'resolve_trauma', 'recharge_trait', 'maintain_bond')"
)
_PROPOSAL_ORIGINS = "('player', 'system')"
_EVENT_ACTOR_TYPES = "('player', 'gm', 'system')"
_EVENT_VISIBILITIES = (
    "('silent', 'gm_only', 'private', 'bonded', 'familiar', 'public', 'global')"
)
_SESSION_STATUSES = "('draft', 'active', 'ended')"
_STORY_STATUSES = "('active', 'completed', 'abandoned')"
_SLOT_TYPES = (
    "('core_trait', 'role_trait', 'pc_bond', 'npc_bond', "
    "'group_trait', 'group_relation', 'group_holding', "
    "'feature_trait', 'location_bond')"
)
_SLOT_OWNER_TYPES = "('character', 'group', 'location')"


def upgrade() -> None:
    """Add CHECK constraints to enum columns and index on events.created_at."""

    # -- proposals -----------------------------------------------------------
    with op.batch_alter_table("proposals") as batch_op:
        batch_op.create_check_constraint(
            "ck_proposals_status",
            f"status IN {_PROPOSAL_STATUSES}",
        )
        batch_op.create_check_constraint(
            "ck_proposals_action_type",
            f"action_type IN {_PROPOSAL_ACTION_TYPES}",
        )
        batch_op.create_check_constraint(
            "ck_proposals_origin",
            f"origin IN {_PROPOSAL_ORIGINS}",
        )

    # -- events --------------------------------------------------------------
    with op.batch_alter_table("events") as batch_op:
        batch_op.create_check_constraint(
            "ck_events_actor_type",
            f"actor_type IN {_EVENT_ACTOR_TYPES}",
        )
        batch_op.create_check_constraint(
            "ck_events_visibility",
            f"visibility IN {_EVENT_VISIBILITIES}",
        )

    # -- sessions ------------------------------------------------------------
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.create_check_constraint(
            "ck_sessions_status",
            f"status IN {_SESSION_STATUSES}",
        )

    # -- stories -------------------------------------------------------------
    with op.batch_alter_table("stories") as batch_op:
        batch_op.create_check_constraint(
            "ck_stories_status",
            f"status IN {_STORY_STATUSES}",
        )

    # -- slots ---------------------------------------------------------------
    with op.batch_alter_table("slots") as batch_op:
        batch_op.create_check_constraint(
            "ck_slots_slot_type",
            f"slot_type IN {_SLOT_TYPES}",
        )
        batch_op.create_check_constraint(
            "ck_slots_owner_type",
            f"owner_type IN {_SLOT_OWNER_TYPES}",
        )

    # -- index on events.created_at for timeline queries --------------------
    op.create_index("ix_events_created_at", "events", ["created_at"])


def downgrade() -> None:
    """Remove CHECK constraints and the events.created_at index."""

    op.drop_index("ix_events_created_at", table_name="events")

    with op.batch_alter_table("slots") as batch_op:
        batch_op.drop_constraint("ck_slots_owner_type", type_="check")
        batch_op.drop_constraint("ck_slots_slot_type", type_="check")

    with op.batch_alter_table("stories") as batch_op:
        batch_op.drop_constraint("ck_stories_status", type_="check")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("ck_sessions_status", type_="check")

    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_constraint("ck_events_visibility", type_="check")
        batch_op.drop_constraint("ck_events_actor_type", type_="check")

    with op.batch_alter_table("proposals") as batch_op:
        batch_op.drop_constraint("ck_proposals_origin", type_="check")
        batch_op.drop_constraint("ck_proposals_action_type", type_="check")
        batch_op.drop_constraint("ck_proposals_status", type_="check")
