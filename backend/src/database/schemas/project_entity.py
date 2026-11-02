from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from database.base import Base
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from database.schemas.test_case_entity import TestCase
    from database.schemas.test_run_entity import TestRun
    from database.schemas.workspace_entity import Workspace


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_projects_workspace_name"),
        UniqueConstraint(
            "workspace_id",
            "repository_provider",
            "repository_id",
            name="uq_projects_workspace_repository",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    repository_url: Mapped[Optional[str]] = mapped_column(String(2048))
    repository_provider: Mapped[Optional[str]] = mapped_column(String(32))
    repository_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    repository_full_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    test_runs: Mapped[list[TestRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list[TestCase]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    workspace: Mapped[Workspace] = relationship(back_populates="projects")
