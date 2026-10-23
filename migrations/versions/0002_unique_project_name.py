"""Enforce unique project names.

Revision ID: 0002_unique_project_name
Revises: 0001_initial_schema
"""

from alembic import op

revision = "0002_unique_project_name"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_projects_name", "projects", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_projects_name", "projects", type_="unique")
