"""add username to users

Revision ID: a1b2c3d4e5f6
Revises: f12345678901
Create Date: 2026-09-17 03:23:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f12345678901'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add username column — nullable so existing users are not broken
    op.add_column('users', sa.Column('username', sa.String(), nullable=True))
    # Create unique index on username (allow NULLs — PostgreSQL allows multiple NULLs in unique index)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_username', table_name='users')
    op.drop_column('users', 'username')
