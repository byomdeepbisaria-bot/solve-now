"""Add auth_otps table for email verification and password reset

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-28 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auth_otps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('purpose', sa.String(), nullable=False),
        sa.Column('otp_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='5', nullable=False),
        sa.Column('is_used', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('reset_token', sa.String(), nullable=True),
        sa.Column('reset_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_otps_email'), 'auth_otps', ['email'], unique=False)
    op.create_index(op.f('ix_auth_otps_purpose'), 'auth_otps', ['purpose'], unique=False)
    op.create_index(op.f('ix_auth_otps_user_id'), 'auth_otps', ['user_id'], unique=False)
    op.create_index(op.f('ix_auth_otps_reset_token'), 'auth_otps', ['reset_token'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_auth_otps_reset_token'), table_name='auth_otps')
    op.drop_index(op.f('ix_auth_otps_user_id'), table_name='auth_otps')
    op.drop_index(op.f('ix_auth_otps_purpose'), table_name='auth_otps')
    op.drop_index(op.f('ix_auth_otps_email'), table_name='auth_otps')
    op.drop_table('auth_otps')
