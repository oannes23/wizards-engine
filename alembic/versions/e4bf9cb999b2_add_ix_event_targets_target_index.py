"""add ix_event_targets_target index

Revision ID: e4bf9cb999b2
Revises: 02a420cce9eb
Create Date: 2026-03-22 19:50:43.111783

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4bf9cb999b2'
down_revision: Union[str, Sequence[str], None] = '02a420cce9eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite index on event_targets(target_type, target_id).

    Supports efficient reverse lookups used by the GM queue summary:
    "recent 3 events for PC X", "recent 3 events for Group Y", and
    "groups sorted by most-recent-event".  Without this index every
    per-entity event query performs a full scan of event_targets.
    """
    op.create_index(
        'ix_event_targets_target',
        'event_targets',
        ['target_type', 'target_id'],
        unique=False,
    )


def downgrade() -> None:
    """Remove composite index ix_event_targets_target."""
    op.drop_index('ix_event_targets_target', table_name='event_targets')
