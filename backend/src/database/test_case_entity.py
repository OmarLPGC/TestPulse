from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base

if TYPE_CHECKING:
    from database.project_entity import Project
    from database.test_result_entity import TestResult


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("project_id", "node_id", name="uq_test_cases_project_node"),
        UniqueConstraint("id", "project_id", name="uq_test_cases_id_project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String(512), nullable=False)
    class_name: Mapped[Optional[str]] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    project: Mapped[Optional[Project]] = relationship(back_populates="test_cases")
    test_results: Mapped[list[TestResult]] = relationship(
        back_populates="test_case", overlaps="test_run,test_results"
    )
