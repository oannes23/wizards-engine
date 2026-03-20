"""rename_bond_stress_to_charges

Rename slots.stress -> charges and slots.stress_degradations -> degradations.
These columns store bond charge counts, not character stress.

Revision ID: a7c3e1f09b22
Revises: f148d620696e
Create Date: 2026-03-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c3e1f09b22'
down_revision: Union[str, Sequence[str], None] = 'f148d620696e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("slots") as batch_op:
        batch_op.alter_column("stress", new_column_name="charges")
        batch_op.alter_column("stress_degradations", new_column_name="degradations")


def downgrade() -> None:
    with op.batch_alter_table("slots") as batch_op:
        batch_op.alter_column("charges", new_column_name="stress")
        batch_op.alter_column("degradations", new_column_name="stress_degradations")
