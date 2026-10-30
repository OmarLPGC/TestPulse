from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from database.base import Base
from database.enums import AnalysisJobStatus
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

DEFAULT_ANALYSIS_JOB_MAX_ATTEMPTS = 3

if TYPE_CHECKING:
    from database.schemas.test_run_entity import TestRun


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["test_run_id", "project_id"],
            ["test_runs.id", "test_runs.project_id"],
            name="fk_analysis_jobs_run_project",
            ondelete="CASCADE",
        ),
        UniqueConstraint("test_run_id", name="uq_analysis_jobs_test_run_id"),
        CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts",
            name="attempts_valid",
        ),
        Index("ix_analysis_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    test_run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AnalysisJobStatus] = mapped_column(
        SAEnum(
            AnalysisJobStatus,
            name="analysis_job_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=AnalysisJobStatus.PENDING,
        server_default=AnalysisJobStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_ANALYSIS_JOB_MAX_ATTEMPTS,
        server_default=str(DEFAULT_ANALYSIS_JOB_MAX_ATTEMPTS),
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    test_run: Mapped[TestRun] = relationship(back_populates="analysis_job")
