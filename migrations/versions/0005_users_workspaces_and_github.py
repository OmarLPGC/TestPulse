"""Add users, workspaces, sessions, and GitHub repository metadata.

Revision ID: 0005_users_workspaces_and_github
Revises: 0004_durable_analysis_jobs
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_users_workspaces_and_github"
down_revision = "0004_durable_analysis_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("github_login", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("github_user_id", name=op.f("uq_users_github_user_id")),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_legacy", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_personal", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "NOT (is_legacy AND is_personal)",
            name=op.f("ck_workspaces_legacy_not_personal"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'member')", name=op.f("ck_workspace_memberships_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_workspace_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_memberships_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_memberships")),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name=op.f("uq_workspace_memberships_workspace_user")
        ),
    )
    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("state_hash", name=op.f("pk_oauth_states")),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("github_access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("github_refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("github_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_user_sessions")),
    )
    op.execute(
        sa.text("INSERT INTO workspaces (name, is_legacy) VALUES ('Legacy workspace', TRUE)")
    )
    op.add_column("projects", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE projects SET workspace_id = "
            "(SELECT id FROM workspaces WHERE is_legacy = TRUE ORDER BY id LIMIT 1)"
        )
    )
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("workspace_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint("uq_projects_name", type_="unique")
        batch_op.create_foreign_key(
            op.f("fk_projects_workspace_id_workspaces"),
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            op.f("uq_projects_workspace_name"), ["workspace_id", "name"]
        )
    op.add_column("projects", sa.Column("repository_provider", sa.String(length=32), nullable=True))
    op.add_column("projects", sa.Column("repository_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "projects", sa.Column("repository_full_name", sa.String(length=255), nullable=True)
    )
    op.create_unique_constraint(
        op.f("uq_projects_workspace_repository"),
        "projects",
        ["workspace_id", "repository_provider", "repository_id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_projects_workspace_repository"), "projects", type_="unique")
    op.drop_column("projects", "repository_full_name")
    op.drop_column("projects", "repository_id")
    op.drop_column("projects", "repository_provider")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint(op.f("uq_projects_workspace_name"), type_="unique")
        batch_op.drop_constraint(op.f("fk_projects_workspace_id_workspaces"), type_="foreignkey")
        batch_op.create_unique_constraint("uq_projects_name", ["name"])
        batch_op.drop_column("workspace_id")
    op.drop_table("user_sessions")
    op.drop_table("oauth_states")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
    op.drop_table("users")
