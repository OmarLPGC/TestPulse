from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.enums import TestOutcome

if TYPE_CHECKING:
    from database.schemas.test_case_entity import TestCase
    from database.schemas.test_run_entity import TestRun


class TestResult(Base):
    __tablename__ = "test_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["test_run_id", "project_id"],
            ["test_runs.id", "test_runs.project_id"],
            name="fk_test_results_run_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["test_case_id", "project_id"],
            ["test_cases.id", "test_cases.project_id"],
            name="fk_test_results_case_project",
            ondelete="CASCADE",
        ),
        UniqueConstraint("test_run_id", "test_case_id", name="uq_test_results_run_case"),
        CheckConstraint("duration IS NULL OR duration >= 0", name="duration_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    test_run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    test_case_id: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[TestOutcome] = mapped_column(
        SAEnum(
            TestOutcome,
            name="test_outcome",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    duration: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    traceback: Mapped[Optional[str]] = mapped_column(Text)

    test_run: Mapped[Optional[TestRun]] = relationship(
        back_populates="test_results", overlaps="test_case,test_results"
    )
    test_case: Mapped[Optional[TestCase]] = relationship(
        back_populates="test_results", overlaps="test_run,test_results"
    )
