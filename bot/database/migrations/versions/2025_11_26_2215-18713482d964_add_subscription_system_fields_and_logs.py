"""Add subscription system fields and logs table

Revision ID: 18713482d964
Revises: 9449d7f40ef0
Create Date: 2025-11-26 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18713482d964'
down_revision: Union[str, None] = '9449d7f40ef0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add subscription fields to users table
    op.add_column('users', sa.Column('subscription_token', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('subscription_created_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('subscription_updated_at', sa.TIMESTAMP(timezone=True), nullable=True))

    # Create unique index on subscription_token
    op.create_index('idx_users_subscription_token', 'users', ['subscription_token'], unique=True)

    # Create subscription_logs table
    op.create_table(
        'subscription_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('servers_count', sa.Integer(), nullable=True),
        sa.Column('accessed_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes on subscription_logs
    op.create_index('idx_subscription_logs_user', 'subscription_logs', ['user_id'])
    op.create_index('idx_subscription_logs_time', 'subscription_logs', ['accessed_at'])


def downgrade() -> None:
    # Drop subscription_logs table and its indexes
    op.drop_index('idx_subscription_logs_time', table_name='subscription_logs')
    op.drop_index('idx_subscription_logs_user', table_name='subscription_logs')
    op.drop_table('subscription_logs')

    # Drop subscription fields from users table
    op.drop_index('idx_users_subscription_token', table_name='users')
    op.drop_column('users', 'subscription_updated_at')
    op.drop_column('users', 'subscription_created_at')
    op.drop_column('users', 'subscription_token')
