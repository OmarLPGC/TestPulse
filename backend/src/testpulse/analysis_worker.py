import logging
from collections.abc import Callable

from database.db_operations.analysis_jobs import (
    claim_next_analysis_job,
    complete_analysis_job,
    fail_analysis_job,
)
from database.db_operations.runs import (
    get_project_test_observations,
    get_run_regression_results,
)
from database.schemas.analysis_job_entity import AnalysisJob
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from testpulse.analysis import (
    DEFAULT_WINDOW_SIZE,
    MINIMUM_OBSERVATIONS,
    analyze_test_reliability,
    detect_regressions,
)

logger = logging.getLogger(__name__)
DEFAULT_JOB_LEASE_SECONDS = 300
MAX_ERROR_MESSAGE_LENGTH = 2000
AnalysisProcessor = Callable[[Session, int], dict[str, object]]


def analyze_run(session: Session, job_id: int) -> dict[str, object]:
    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise ValueError(f"Analysis job {job_id} no longer exists.")

    run_data = get_run_regression_results(session, job.project_id, job.test_run_id)
    if run_data is None:
        raise ValueError(f"Test run {job.test_run_id} no longer exists.")
    current_run, previous_run, current_results, previous_results = run_data

    regressions = detect_regressions(
        current_run_results=current_results,
        previous_run_results=previous_results,
    )
    observations = get_project_test_observations(
        session,
        job.project_id,
        branch=current_run.branch,
        window_size=DEFAULT_WINDOW_SIZE,
        through_run=current_run,
    )
    reliability_by_test = {
        analysis.test_case_id: analysis
        for analysis in analyze_test_reliability(
            observations,
            window_size=DEFAULT_WINDOW_SIZE,
            minimum_observations=MINIMUM_OBSERVATIONS,
        )
    }
    current_test_ids = {result.test_case_id for result in current_results}

    return {
        "window_size": DEFAULT_WINDOW_SIZE,
        "minimum_observations": MINIMUM_OBSERVATIONS,
        "branch": current_run.branch,
        "previous_run_id": previous_run.id if previous_run else None,
        "reliability": [
            {
                "test_case_id": analysis.test_case_id,
                "name": analysis.name,
                "class_name": analysis.class_name,
                "observations": analysis.observations,
                "passed": analysis.passed,
                "failed": analysis.failed,
                "errors": analysis.errors,
                "failure_rate": analysis.failure_rate,
                "reliability": analysis.reliability.value,
                "potentially_flaky": analysis.potentially_flaky,
            }
            for test_case_id, analysis in sorted(reliability_by_test.items())
            if test_case_id in current_test_ids
        ],
        "regressions": [
            {
                "test_case_id": regression.test_case_id,
                "name": regression.name,
                "class_name": regression.class_name,
                "previous_outcome": regression.previous_outcome.value,
                "current_outcome": regression.current_outcome.value,
            }
            for regression in regressions
        ],
    }


def process_next_analysis_job(
    engine: Engine,
    *,
    processor: AnalysisProcessor = analyze_run,
    lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
) -> bool:
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1.")

    with Session(engine) as session, session.begin():
        claim = claim_next_analysis_job(session, lease_seconds=lease_seconds)
    if claim is None:
        return False

    job_id, attempt = claim
    try:
        with Session(engine) as session:
            result = processor(session, job_id)
        with Session(engine) as session, session.begin():
            completed = complete_analysis_job(
                session,
                job_id=job_id,
                attempt=attempt,
                result=result,
            )
        if not completed:
            logger.warning(
                "Discarded stale result for analysis job %s, attempt %s.",
                job_id,
                attempt,
            )
    except Exception as error:
        error_details = " ".join(str(error).split())
        error_message = f"{type(error).__name__}: {error_details}"[:MAX_ERROR_MESSAGE_LENGTH]
        logger.exception("Analysis job %s failed on attempt %s.", job_id, attempt)
        with Session(engine) as session, session.begin():
            status = fail_analysis_job(
                session,
                job_id=job_id,
                attempt=attempt,
                error_message=error_message,
            )
        if status is not None:
            logger.info("Analysis job %s moved to %s.", job_id, status.value)
    return True
