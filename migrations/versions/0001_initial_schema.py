"""Create project and test result tables.

Revision ID: 0001_initial_schema
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("repository_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=512), nullable=False),
        sa.Column("class_name", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_test_cases_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_cases"),
        sa.UniqueConstraint("id", "project_id", name="uq_test_cases_id_project_id"),
        sa.UniqueConstraint("project_id", "node_id", name="uq_test_cases_project_node"),
    )
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=True),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("report_sha", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=9),
            server_default="pending",
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration IS NULL OR duration >= 0",
            name="ck_test_runs_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_test_runs_test_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_test_runs_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_runs"),
        sa.UniqueConstraint("id", "project_id", name="uq_test_runs_id_project_id"),
    )
    op.create_table(
        "test_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("test_run_id", sa.Integer(), nullable=False),
        sa.Column("test_case_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=7), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "duration IS NULL OR duration >= 0",
            name="ck_test_results_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "outcome IN ('passed', 'failed', 'skipped', 'error')",
            name="ck_test_results_test_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["test_case_id", "project_id"],
            ["test_cases.id", "test_cases.project_id"],
            name="fk_test_results_case_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id", "project_id"],
            ["test_runs.id", "test_runs.project_id"],
            name="fk_test_results_run_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_results"),
        sa.UniqueConstraint("test_run_id", "test_case_id", name="uq_test_results_run_case"),
    )


def downgrade() -> None:
    op.drop_table("test_results")
    op.drop_table("test_runs")
    op.drop_table("test_cases")
    op.drop_table("projects")
