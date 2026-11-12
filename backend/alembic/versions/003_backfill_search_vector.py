"""Ensure search_vector trigger exists and backfill existing document_chunks rows.

Revision ID: 003
Revises: 002
Create Date: 2026-11-12
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector := to_tsvector('simple', COALESCE(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_search_vector ON document_chunks")
    op.execute(
        """
        CREATE TRIGGER trg_chunks_search_vector
        BEFORE INSERT OR UPDATE OF content ON document_chunks
        FOR EACH ROW EXECUTE FUNCTION update_search_vector();
        """
    )
    op.execute(
        """
        UPDATE document_chunks
        SET search_vector = to_tsvector('simple', COALESCE(content, ''))
        WHERE search_vector IS NULL;
        """
    )


def downgrade() -> None:
    pass
