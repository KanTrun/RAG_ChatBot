"""Add active document ids to conversations.

Revision ID: 002
Revises: 001
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "active_document_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
    )
    op.alter_column("conversations", "active_document_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("conversations", "active_document_ids")
