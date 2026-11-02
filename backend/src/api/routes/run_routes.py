from typing import Optional

from database.db_operations.ingestion_tokens import authenticate_ingestion_token
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
from database.schemas.user_entity import User
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session
from testpulse.junit_parser import JUnitReportError, parse_junit_xml

from api.authz import require_project_member
from api.dependencies import get_current_user, get_db_session
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
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    ci_source: Optional[str] = Header(default=None, alias="X-CI-Source"),
    ci_run_id: Optional[str] = Header(default=None, alias="X-CI-Run-ID"),
    ci_run_attempt: Optional[str] = Header(default=None, alias="X-CI-Run-Attempt"),
    ci_event: Optional[str] = Header(default=None, alias="X-CI-Event"),
    ci_pull_request: Optional[str] = Header(default=None, alias="X-CI-Pull-Request"),
) -> TestRunRead:
    scheme, _, raw_token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not raw_token.strip() or len(raw_token) > 512:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A project ingestion token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authenticate_ingestion_token(session, project_id, raw_token.strip())
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Project ingestion token is invalid, expired, or revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = request.app.state.settings
    metadata_limits = {
        "X-CI-Source": (ci_source, 100),
        "X-CI-Run-ID": (ci_run_id, 255),
        "X-CI-Run-Attempt": (ci_run_attempt, 64),
        "X-CI-Event": (ci_event, 100),
        "X-CI-Pull-Request": (ci_pull_request, 64),
    }
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
    for header, (value, limit) in metadata_limits.items():
        if value is not None and (not value.strip() or len(value) > limit):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{header} must contain 1 to {limit} non-whitespace characters.",
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
            project_id=project_id,
            report=report,
            report_content=report_content,
            commit_sha=commit_sha,
            branch=branch,
            idempotency_key=idempotency_key.strip() if idempotency_key else None,
            ci_source=ci_source,
            ci_run_id=ci_run_id,
            ci_run_attempt=ci_run_attempt,
            ci_event=ci_event,
            ci_pull_request=ci_pull_request,
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
        ci_source=loaded_run.ci_source,
        ci_run_id=loaded_run.ci_run_id,
        ci_run_attempt=loaded_run.ci_run_attempt,
        ci_event=loaded_run.ci_event,
        ci_pull_request=loaded_run.ci_pull_request,
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
    current_user: User = Depends(get_current_user),
) -> TestRunHistoryPage:
    require_project_member(session, project_id, current_user)

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
    current_user: User = Depends(get_current_user),
) -> TestRunSummaryRead:
    require_project_member(session, project_id, current_user)

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
    current_user: User = Depends(get_current_user),
) -> TestResultPage:
    require_project_member(session, project_id, current_user)
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
