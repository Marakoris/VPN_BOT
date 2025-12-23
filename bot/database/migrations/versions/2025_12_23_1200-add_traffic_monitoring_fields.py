"""Add traffic monitoring fields

Revision ID: add_traffic_monitoring
Revises: 18713482d964
Create Date: 2025-12-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_traffic_monitoring'
down_revision: Union[str, None] = '18713482d964'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add traffic monitoring fields to users table
    op.add_column('users', sa.Column('total_traffic_bytes', sa.BigInteger(), nullable=True, server_default='0'))
    op.add_column('users', sa.Column('traffic_reset_date', sa.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('users', sa.Column('traffic_limit_bytes', sa.BigInteger(), nullable=True, server_default='536870912000'))  # 500GB


def downgrade() -> None:
    op.drop_column('users', 'traffic_limit_bytes')
    op.drop_column('users', 'traffic_reset_date')
    op.drop_column('users', 'total_traffic_bytes')
