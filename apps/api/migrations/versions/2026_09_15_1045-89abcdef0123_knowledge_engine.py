"""Knowledge engine and pgvector

Revision ID: 89abcdef0123
Revises: def012345678
Create Date: 2026-09-15 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '89abcdef0123'
down_revision: Union[str, None] = 'def012345678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pgvector_available(conn) -> bool:
    """Check if pgvector is installable without executing DDL that could abort the transaction."""
    try:
        result = conn.execute(sa.text(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        ))
        if result.fetchone():
            # Available — now install it
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            return True
        return False
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Try to enable pgvector — skip silently if not installed
    use_vector = _pgvector_available(conn)

    # 2. Add embedding to problems — use vector if available, else FLOAT[]
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='problems' AND column_name='embedding'"
    ))
    if not result.fetchone():
        if use_vector:
            conn.execute(sa.text(
                "ALTER TABLE problems ADD COLUMN embedding vector(768)"
            ))
        else:
            conn.execute(sa.text(
                "ALTER TABLE problems ADD COLUMN embedding FLOAT[]"
            ))

    # 3. Create Enum
    knowledge_status = postgresql.ENUM('DRAFT', 'PUBLISHED', 'ARCHIVED', 'FLAGGED', name='knowledgestatus', create_type=False)
    knowledge_status.create(op.get_bind())

    # 4. Create KnowledgeDocument — use vector or FLOAT[] for embedding
    embedding_col = (
        sa.Column('embedding', sa.Text(), nullable=True)  # placeholder; actual type set below
    )
    op.create_table('knowledge_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', knowledge_status, nullable=False),
        sa.Column('quality_score', sa.Integer(), nullable=True),
        sa.Column('verification_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['problem_categories.id']),
        sa.PrimaryKeyConstraint('id')
    )
    # Add embedding column with right type
    if use_vector:
        conn.execute(sa.text(
            "ALTER TABLE knowledge_documents ADD COLUMN embedding vector(768)"
        ))
    else:
        conn.execute(sa.text(
            "ALTER TABLE knowledge_documents ADD COLUMN embedding FLOAT[]"
        ))

    # 5. Create KnowledgeSource
    op.create_table('knowledge_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('knowledge_document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('problem_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('solution_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['knowledge_document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['problem_id'], ['problems.id']),
        sa.ForeignKeyConstraint(['solution_id'], ['solutions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. Create KnowledgeVersion
    op.create_table('knowledge_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('knowledge_document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_diff', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['knowledge_document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    pass
