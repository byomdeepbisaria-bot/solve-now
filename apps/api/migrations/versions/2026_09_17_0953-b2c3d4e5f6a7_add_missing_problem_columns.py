"""Add missing problem columns: embedding, is_hidden, is_locked

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-17 09:53:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add is_hidden column if it doesn't exist
    _add_column_if_missing(conn, 'problems', 'is_hidden',
        'ALTER TABLE problems ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE')

    # Add is_locked column if it doesn't exist
    _add_column_if_missing(conn, 'problems', 'is_locked',
        'ALTER TABLE problems ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT FALSE')

    # Add embedding as FLOAT[] (no pgvector needed)
    # If pgvector is later installed, this can be converted to vector type
    _add_column_if_missing(conn, 'problems', 'embedding',
        'ALTER TABLE problems ADD COLUMN embedding FLOAT[]')

    # Add scan_status to problem_files if missing
    _add_column_if_missing(conn, 'problem_files', 'scan_status',
        "ALTER TABLE problem_files ADD COLUMN scan_status VARCHAR NOT NULL DEFAULT 'PENDING'")

    # Fix problem_files columns — original migration used wrong names
    _add_column_if_missing(conn, 'problem_files', 'storage_key',
        'ALTER TABLE problem_files ADD COLUMN storage_key VARCHAR')
    _add_column_if_missing(conn, 'problem_files', 'original_name',
        'ALTER TABLE problem_files ADD COLUMN original_name VARCHAR')
    _add_column_if_missing(conn, 'problem_files', 'mime_type',
        'ALTER TABLE problem_files ADD COLUMN mime_type VARCHAR')
    _add_column_if_missing(conn, 'problem_files', 'size',
        'ALTER TABLE problem_files ADD COLUMN size INTEGER')
    _add_column_if_missing(conn, 'problem_files', 'sha256',
        'ALTER TABLE problem_files ADD COLUMN sha256 VARCHAR')
    _add_column_if_missing(conn, 'problem_files', 'owner_id',
        'ALTER TABLE problem_files ADD COLUMN owner_id UUID REFERENCES users(id) ON DELETE CASCADE')


def _add_column_if_missing(conn, table: str, column: str, ddl: str):
    """Only run DDL if column doesn't already exist."""
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    if not result.fetchone():
        conn.execute(sa.text(ddl))


def downgrade() -> None:
    # Intentionally empty — don't drop data on downgrade
    pass
