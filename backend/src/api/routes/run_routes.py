from typing import Optional

from database.db_operations.projects import get_project
from database.db_operations.runs import (
    RunIngestionConflict,
    RunIngestionValidationError,
    count_project_runs,
    count_run_results,
    get_project_run,
    get_project_run_summary,
    get_test_run_with_results,
    ingest_test_run,
    list_project_runs,
    list_run_results,
)
from database.enums import TestOutcome
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session
from testpulse.junit_parser import JUnitReportError, parse_junit_xml

from api.routes.project_routes import get_db_session
from api.schemas.run_schemas import (
    TestResultPage,
    TestResultRead,
    TestRunHistoryItem,
    TestRunHistoryPage,
    TestRunRead,
    TestRunSummaryRead,
)

router = APIRouter(prefix="/api/v1/projects", tags=["test-runs"])


async def _read_report(request: Request, max_bytes: int) -> bytes:
    report_parts = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"JUnit report exceeds the {max_bytes}-byte limit.",
            )
        report_parts.append(chunk)
    return b"".join(report_parts)


@router.post(
    "/{project_id}/runs",
    response_model=TestRunRead,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/xml": {"schema": {"type": "string"}},
                "text/xml": {"schema": {"type": "string"}},
            },
        }
    },
)
async def ingest_run_endpoint(
    project_id: int,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
    commit_sha: Optional[str] = Header(default=None, alias="X-Commit-SHA"),
    branch: Optional[str] = Header(default=None, alias="X-Branch"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> TestRunRead:
    project = get_project(session, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    settings = request.app.state.settings
    if commit_sha is not None and len(commit_sha) > 40:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="X-Commit-SHA must not exceed 40 characters.",
        )
    if branch is not None and len(branch) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="X-Branch must not exceed 255 characters.",
        )
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 255):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key must contain 1 to 255 non-whitespace characters.",
        )

    report_content = await _read_report(request, settings.max_junit_report_bytes)
    try:
        report = parse_junit_xml(
            report_content,
            max_xml_bytes=settings.max_junit_report_bytes,
            max_test_cases=settings.max_junit_test_cases,
        )
    except JUnitReportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    try:
        run, created = ingest_test_run(
            session,
            project_id=project.id,
            report=report,
            report_content=report_content,
            commit_sha=commit_sha,
            branch=branch,
            idempotency_key=idempotency_key.strip() if idempotency_key else None,
        )
    except RunIngestionConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different report or metadata.",
        ) from error
    except RunIngestionValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    if not created:
        response.status_code = status.HTTP_200_OK
    loaded_run = get_test_run_with_results(session, run.id)
    if loaded_run is None:
        raise RuntimeError("Persisted test run could not be loaded.")
    return TestRunRead(
        id=loaded_run.id,
        project_id=loaded_run.project_id,
        commit_sha=loaded_run.commit_sha,
        branch=loaded_run.branch,
        report_sha=loaded_run.report_sha,
        status=loaded_run.status,
        duration=loaded_run.duration,
        test_results=[
            TestResultRead(
                id=result.id,
                test_case_id=result.test_case_id,
                name=result.test_case.name,
                class_name=result.test_case.class_name,
                outcome=result.outcome,
                duration=result.duration,
                error_message=result.error_message,
                traceback=result.traceback,
            )
            for result in loaded_run.test_results
        ],
    )


@router.get("/{project_id}/runs", response_model=TestRunHistoryPage)
def list_runs_endpoint(
    project_id: int,
    branch: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> TestRunHistoryPage:
    if get_project(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    runs = list_project_runs(session, project_id, branch=branch, limit=limit, offset=offset)
    return TestRunHistoryPage(
        items=[TestRunHistoryItem.model_validate(run) for run in runs],
        limit=limit,
        offset=offset,
        total=count_project_runs(session, project_id, branch=branch),
    )


@router.get("/{project_id}/runs/{run_id}", response_model=TestRunSummaryRead)
def get_run_summary_endpoint(
    project_id: int,
    run_id: int,
    session: Session = Depends(get_db_session),
) -> TestRunSummaryRead:
    if get_project(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    summary = get_project_run_summary(session, project_id, run_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )
    return TestRunSummaryRead(
        id=summary.run.id,
        project_id=summary.run.project_id,
        commit_sha=summary.run.commit_sha,
        branch=summary.run.branch,
        report_sha=summary.run.report_sha,
        status=summary.run.status,
        duration=summary.run.duration,
        ingested_at=summary.run.ingested_at,
        completed_at=summary.run.completed_at,
        total=summary.total,
        passed=summary.passed,
        failed=summary.failed,
        skipped=summary.skipped,
        error=summary.error,
    )


@router.get(
    "/{project_id}/runs/{run_id}/results",
    response_model=TestResultPage,
)
def get_run_results_endpoint(
    project_id: int,
    run_id: int,
    outcome: Optional[TestOutcome] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> TestResultPage:
    if get_project(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    run = get_project_run(session, project_id, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    results = list_run_results(session, run_id, outcome=outcome, limit=limit, offset=offset)
    return TestResultPage(
        items=[
            TestResultRead(
                id=result.id,
                test_case_id=result.test_case_id,
                name=result.test_case.name,
                class_name=result.test_case.class_name,
                outcome=result.outcome,
                duration=result.duration,
                error_message=result.error_message,
                traceback=result.traceback,
            )
            for result in results
        ],
        limit=limit,
        offset=offset,
        total=count_run_results(session, run_id, outcome=outcome),
    )
