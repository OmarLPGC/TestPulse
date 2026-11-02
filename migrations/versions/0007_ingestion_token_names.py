"""Add names to project ingestion tokens.

Revision ID: 0007_ingestion_token_names
Revises: 0006_ci_ingestion_tokens
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_ingestion_token_names"
down_revision = "0006_ci_ingestion_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_ingestion_tokens",
        sa.Column("name", sa.String(length=100), nullable=True),
    )
    op.execute(
        "UPDATE project_ingestion_tokens SET name = 'Ingestion token ' || CAST(id AS VARCHAR)"
    )
    op.alter_column("project_ingestion_tokens", "name", nullable=False)


def downgrade() -> None:
    op.drop_column("project_ingestion_tokens", "name")
