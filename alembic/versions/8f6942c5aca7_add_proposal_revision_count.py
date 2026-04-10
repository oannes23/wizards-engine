"""add_proposal_revision_count

Revision ID: 8f6942c5aca7
Revises: c4a94a3e3cf9
Create Date: 2026-04-02 23:45:33.047560

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f6942c5aca7'
down_revision: Union[str, Sequence[str], None] = 'c4a94a3e3cf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add revision_count to proposals table."""
    with op.batch_alter_table("proposals") as batch_op:
        batch_op.add_column(
            sa.Column("revision_count", sa.Integer(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    """Remove revision_count from proposals table."""
    with op.batch_alter_table("proposals") as batch_op:
        batch_op.drop_column("revision_count")
