from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from database.enums import AnalysisJobStatus
from database.schemas.analysis_job_entity import AnalysisJob


def get_run_analysis_job(
    session: Session, project_id: int, test_run_id: int
) -> Optional[AnalysisJob]:
    return session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.project_id == project_id,
            AnalysisJob.test_run_id == test_run_id,
        )
    )


def claim_next_analysis_job(
    session: Session,
    *,
    lease_seconds: int,
    now: Optional[datetime] = None,
) -> Optional[tuple[int, int]]:
    claimed_at = now or datetime.now(timezone.utc)
    expired_processing = and_(
        AnalysisJob.status == AnalysisJobStatus.PROCESSING,
        AnalysisJob.lease_expires_at <= claimed_at,
    )
    session.execute(
        update(AnalysisJob)
        .where(
            expired_processing,
            AnalysisJob.attempts >= AnalysisJob.max_attempts,
        )
        .values(
            status=AnalysisJobStatus.FAILED,
            last_error=func.coalesce(
                AnalysisJob.last_error,
                "Worker lease expired after the maximum number of attempts.",
            ),
            updated_at=claimed_at,
            completed_at=claimed_at,
            lease_expires_at=None,
        )
    )
    session.execute(
        update(AnalysisJob)
        .where(
            AnalysisJob.status == AnalysisJobStatus.PENDING,
            AnalysisJob.attempts >= AnalysisJob.max_attempts,
        )
        .values(
            status=AnalysisJobStatus.FAILED,
            last_error=func.coalesce(
                AnalysisJob.last_error,
                "Job reached the maximum number of attempts before processing.",
            ),
            updated_at=claimed_at,
            completed_at=claimed_at,
            lease_expires_at=None,
        )
    )

    job = session.scalar(
        select(AnalysisJob)
        .where(
            or_(
                AnalysisJob.status == AnalysisJobStatus.PENDING,
                and_(
                    expired_processing,
                    AnalysisJob.attempts < AnalysisJob.max_attempts,
                ),
            )
        )
        .order_by(AnalysisJob.created_at.asc(), AnalysisJob.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None

    job.status = AnalysisJobStatus.PROCESSING
    job.attempts += 1
    job.started_at = claimed_at
    job.updated_at = claimed_at
    job.completed_at = None
    job.lease_expires_at = claimed_at + timedelta(seconds=lease_seconds)
    session.flush()
    return job.id, job.attempts


def complete_analysis_job(
    session: Session,
    *,
    job_id: int,
    attempt: int,
    result: dict[str, object],
    now: Optional[datetime] = None,
) -> bool:
    completed_at = now or datetime.now(timezone.utc)
    updated = session.execute(
        update(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.status == AnalysisJobStatus.PROCESSING,
            AnalysisJob.attempts == attempt,
        )
        .values(
            status=AnalysisJobStatus.COMPLETED,
            result=result,
            last_error=None,
            updated_at=completed_at,
            completed_at=completed_at,
            lease_expires_at=None,
        )
    )
    return updated.rowcount == 1


def fail_analysis_job(
    session: Session,
    *,
    job_id: int,
    attempt: int,
    error_message: str,
    now: Optional[datetime] = None,
) -> Optional[AnalysisJobStatus]:
    failed_at = now or datetime.now(timezone.utc)
    job = session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.id == job_id,
            AnalysisJob.status == AnalysisJobStatus.PROCESSING,
            AnalysisJob.attempts == attempt,
        )
    )
    if job is None:
        return None

    job.last_error = error_message
    job.updated_at = failed_at
    job.lease_expires_at = None
    if attempt >= job.max_attempts:
        job.status = AnalysisJobStatus.FAILED
        job.completed_at = failed_at
    else:
        job.status = AnalysisJobStatus.PENDING
        job.completed_at = None
    session.flush()
    return job.status
