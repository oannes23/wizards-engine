"""add viewer role and invite role column

Adds a ``role`` column to the ``invites`` table (default 'player') and
CHECK constraints on both ``invites.role`` and ``users.role`` to enforce the
now-supported role values: 'gm', 'player', 'viewer'.

SQLite does not support plain ALTER TABLE ADD CONSTRAINT, so batch operations
(copy-alter strategy) are used throughout.

Revision ID: c4a94a3e3cf9
Revises: e4bf9cb999b2
Create Date: 2026-03-28 00:06:58.774893

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a94a3e3cf9'
down_revision: Union[str, Sequence[str], None] = 'e4bf9cb999b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add invites.role column and CHECK constraints on role columns."""

    # -- invites: add role column and CHECK constraint -----------------------
    with op.batch_alter_table("invites") as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(10), nullable=False, server_default="player")
        )
        batch_op.create_check_constraint(
            "ck_invites_role", "role IN ('player', 'viewer')"
        )

    # -- users: add CHECK constraint on existing role column -----------------
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role", "role IN ('gm', 'player', 'viewer')"
        )


def downgrade() -> None:
    """Remove CHECK constraints and drop invites.role column."""

    # -- users: drop CHECK constraint ----------------------------------------
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")

    # -- invites: drop CHECK constraint and role column ----------------------
    with op.batch_alter_table("invites") as batch_op:
        batch_op.drop_constraint("ck_invites_role", type_="check")
        batch_op.drop_column("role")
