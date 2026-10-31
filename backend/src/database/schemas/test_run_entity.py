from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from database.base import Base
from database.enums import TestRunStatus
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from database.schemas.analysis_job_entity import AnalysisJob
    from database.schemas.project_entity import Project
    from database.schemas.test_result_entity import TestResult


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_test_runs_id_project_id"),
        UniqueConstraint(
            "project_id", "idempotency_key", name="uq_test_runs_project_idempotency_key"
        ),
        CheckConstraint("duration IS NULL OR duration >= 0", name="duration_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    branch: Mapped[Optional[str]] = mapped_column(String(255))
    report_sha: Mapped[Optional[str]] = mapped_column(String(64))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255))
    request_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    duration: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[TestRunStatus] = mapped_column(
        SAEnum(
            TestRunStatus,
            name="test_run_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=TestRunStatus.PENDING,
        server_default=TestRunStatus.PENDING.value,
    )

    project: Mapped[Optional[Project]] = relationship(back_populates="test_runs")
    test_results: Mapped[list[TestResult]] = relationship(
        back_populates="test_run",
        cascade="all, delete-orphan",
        overlaps="test_case,test_results",
    )
    analysis_job: Mapped[Optional[AnalysisJob]] = relationship(
        back_populates="test_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
