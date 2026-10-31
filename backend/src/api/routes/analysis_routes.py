from typing import Optional

from database.db_operations.projects import get_project
from database.db_operations.runs import (
    get_project_test_observations,
    get_run_regression_results,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from testpulse.analysis import (
    DEFAULT_WINDOW_SIZE,
    MINIMUM_OBSERVATIONS,
    analyze_test_reliability,
    detect_regressions,
)

from api.routes.project_routes import get_db_session
from api.schemas.analysis_schemas import (
    RegressionRead,
    RunRegressionReport,
    TestReliabilityRead,
    TestReliabilityReport,
)

router = APIRouter(prefix="/api/v1/projects", tags=["analysis"])

MAX_WINDOW_SIZE = 100


@router.get(
    "/{project_id}/analysis/reliability",
    response_model=TestReliabilityReport,
)
def get_test_reliability_endpoint(
    project_id: int,
    branch: Optional[str] = None,
    window_size: int = Query(default=DEFAULT_WINDOW_SIZE, ge=1, le=MAX_WINDOW_SIZE),
    session: Session = Depends(get_db_session),
) -> TestReliabilityReport:
    if get_project(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    observations = get_project_test_observations(
        session,
        project_id,
        branch=branch,
        window_size=window_size,
    )
    analyses = analyze_test_reliability(
        observations,
        window_size=window_size,
        minimum_observations=MINIMUM_OBSERVATIONS,
    )
    return TestReliabilityReport(
        branch=branch,
        window_size=window_size,
        minimum_observations=MINIMUM_OBSERVATIONS,
        tests=[
            TestReliabilityRead(
                test_case_id=analysis.test_case_id,
                name=analysis.name,
                class_name=analysis.class_name,
                observations=analysis.observations,
                passed=analysis.passed,
                failed=analysis.failed,
                errors=analysis.errors,
                failure_rate=analysis.failure_rate,
                reliability=analysis.reliability,
                potentially_flaky=analysis.potentially_flaky,
            )
            for analysis in analyses
        ],
    )


@router.get(
    "/{project_id}/runs/{run_id}/regressions",
    response_model=RunRegressionReport,
)
def get_run_regressions_endpoint(
    project_id: int,
    run_id: int,
    session: Session = Depends(get_db_session),
) -> RunRegressionReport:
    if get_project(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    run_data = get_run_regression_results(session, project_id, run_id)
    if run_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    current_run, previous_run, current_results, previous_results = run_data
    regressions = detect_regressions(
        current_run_results=current_results,
        previous_run_results=previous_results,
    )
    return RunRegressionReport(
        project_id=project_id,
        run_id=run_id,
        branch=current_run.branch,
        previous_run_id=previous_run.id if previous_run else None,
        regressions=[
            RegressionRead(
                test_case_id=regression.test_case_id,
                name=regression.name,
                class_name=regression.class_name,
                previous_outcome=regression.previous_outcome,
                current_outcome=regression.current_outcome,
            )
            for regression in regressions
        ],
    )
