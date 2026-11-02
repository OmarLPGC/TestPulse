"""Add project-scoped ingestion tokens and CI metadata.

Revision ID: 0006_ci_ingestion_tokens
Revises: 0005_users_workspaces_and_github
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_ci_ingestion_tokens"
down_revision = "0005_users_workspaces_and_github"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("ci_source", sa.String(length=100), nullable=True))
    op.add_column("test_runs", sa.Column("ci_run_id", sa.String(length=255), nullable=True))
    op.add_column("test_runs", sa.Column("ci_run_attempt", sa.String(length=64), nullable=True))
    op.add_column("test_runs", sa.Column("ci_event", sa.String(length=100), nullable=True))
    op.add_column("test_runs", sa.Column("ci_pull_request", sa.String(length=64), nullable=True))
    op.create_table(
        "project_ingestion_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_ingestion_tokens_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_ingestion_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_project_ingestion_tokens_token_hash")),
    )
    op.create_index(
        "ix_project_ingestion_tokens_project_id", "project_ingestion_tokens", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_project_ingestion_tokens_project_id", table_name="project_ingestion_tokens")
    op.drop_table("project_ingestion_tokens")
    op.drop_column("test_runs", "ci_pull_request")
    op.drop_column("test_runs", "ci_event")
    op.drop_column("test_runs", "ci_run_attempt")
    op.drop_column("test_runs", "ci_run_id")
    op.drop_column("test_runs", "ci_source")
