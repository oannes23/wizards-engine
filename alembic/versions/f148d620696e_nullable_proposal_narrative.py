"""nullable_proposal_narrative

Revision ID: f148d620696e
Revises: b34ed29cf3a3
Create Date: 2026-03-18 22:15:10.851383

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f148d620696e'
down_revision: Union[str, Sequence[str], None] = 'b34ed29cf3a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make proposals.narrative nullable.

    Session action types (use_skill, use_magic, charge_magic) no longer
    require a narrative on submission.  Enforcement for downtime types
    is handled at the application layer (Pydantic validator).
    """
    with op.batch_alter_table("proposals") as batch_op:
        batch_op.alter_column("narrative", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    """Revert proposals.narrative to NOT NULL."""
    with op.batch_alter_table("proposals") as batch_op:
        batch_op.alter_column("narrative", existing_type=sa.Text(), nullable=False)
