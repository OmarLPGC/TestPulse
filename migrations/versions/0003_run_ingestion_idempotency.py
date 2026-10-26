"""Add run ingestion idempotency and empty status.

Revision ID: 0003_run_ingestion_idempotency
Revises: 0002_unique_project_name
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_run_ingestion_idempotency"
down_revision = "0002_unique_project_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_runs", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column(
        "test_runs", sa.Column("request_fingerprint", sa.String(length=64), nullable=True)
    )
    with op.batch_alter_table("test_runs") as batch_op:
        batch_op.drop_constraint(op.f("ck_test_runs_ck_test_runs_test_run_status"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_test_runs_test_run_status"),
            "status IN ('pending', 'running', 'completed', 'failed', 'empty')",
        )
        batch_op.create_unique_constraint(
            op.f("uq_test_runs_project_idempotency_key"),
            ["project_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("test_runs") as batch_op:
        batch_op.drop_constraint(op.f("ck_test_runs_test_run_status"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_test_runs_ck_test_runs_test_run_status"),
            "status IN ('pending', 'running', 'completed', 'failed')",
        )
        batch_op.drop_constraint(op.f("uq_test_runs_project_idempotency_key"), type_="unique")
    op.drop_column("test_runs", "request_fingerprint")
    op.drop_column("test_runs", "idempotency_key")
