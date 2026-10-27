import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from testpulse.junit_parser import ParsedJUnitReport, ParsedTestCase

from database.enums import TestOutcome, TestRunStatus
from database.schemas.test_case_entity import TestCase
from database.schemas.test_result_entity import TestResult
from database.schemas.test_run_entity import TestRun


class RunIngestionConflict(Exception):
    """Raised when an idempotency key is reused for a different request."""


class RunIngestionValidationError(ValueError):
    """Raised when parsed test identity cannot be represented by the database schema."""


def ingest_test_run(
    session: Session,
    *,
    project_id: int,
    report: ParsedJUnitReport,
    report_content: bytes,
    commit_sha: Optional[str],
    branch: Optional[str],
    idempotency_key: Optional[str],
) -> tuple[TestRun, bool]:
    request_fingerprint = _request_fingerprint(report_content, commit_sha, branch)
    existing = _find_idempotent_run(session, project_id, idempotency_key)
    if existing is not None:
        _ensure_same_request(existing, request_fingerprint)
        return existing, False

    node_ids = {test_case.identity: _node_id(test_case) for test_case in report.test_cases}
    status = _run_status(report.test_cases)
    durations = [test_case.duration_ms for test_case in report.test_cases]
    duration = sum(durations) if all(value is not None for value in durations) else None
    if duration is not None and duration > 2_147_483_647:
        raise RunIngestionValidationError("Total test run duration exceeds the supported maximum.")
    run = TestRun(
        project_id=project_id,
        commit_sha=commit_sha,
        branch=branch,
        report_sha=hashlib.sha256(report_content).hexdigest(),
        request_fingerprint=request_fingerprint,
        idempotency_key=idempotency_key,
        duration=duration,
        status=status,
    )

    try:
        with session.begin_nested():
            session.add(run)
            session.flush()
            case_ids = _ensure_test_cases(session, project_id, report.test_cases, node_ids)
            session.add_all(
                [
                    TestResult(
                        project_id=project_id,
                        test_run_id=run.id,
                        test_case_id=case_ids[test_case.identity],
                        outcome=TestOutcome(test_case.outcome.value),
                        duration=test_case.duration_ms,
                        error_message=test_case.error_message,
                        traceback=test_case.traceback,
                    )
                    for test_case in report.test_cases
                ]
            )
            session.flush()
    except IntegrityError:
        if idempotency_key is None:
            raise
        existing = _find_idempotent_run(session, project_id, idempotency_key)
        if existing is None:
            raise
        _ensure_same_request(existing, request_fingerprint)
        return existing, False

    return run, True


def get_test_run_with_results(session: Session, run_id: int) -> Optional[TestRun]:
    return session.scalar(
        select(TestRun)
        .where(TestRun.id == run_id)
        .options(selectinload(TestRun.test_results).joinedload(TestResult.test_case))
    )


def _find_idempotent_run(
    session: Session, project_id: int, idempotency_key: Optional[str]
) -> Optional[TestRun]:
    if idempotency_key is None:
        return None
    return session.scalar(
        select(TestRun)
        .where(
            TestRun.project_id == project_id,
            TestRun.idempotency_key == idempotency_key,
        )
        .options(selectinload(TestRun.test_results).joinedload(TestResult.test_case))
    )


def _ensure_same_request(run: TestRun, request_fingerprint: str) -> None:
    if run.request_fingerprint != request_fingerprint:
        raise RunIngestionConflict


def _ensure_test_cases(
    session: Session,
    project_id: int,
    parsed_cases: Sequence[ParsedTestCase],
    node_ids: dict[tuple[Optional[str], str], str],
) -> dict[tuple[Optional[str], str], int]:
    if not parsed_cases:
        return {}

    dialect = session.get_bind().dialect.name
    insert_statement = {
        "postgresql": postgresql_insert,
        "sqlite": sqlite_insert,
    }.get(dialect)
    if insert_statement is None:
        raise RuntimeError(f"Unsupported database dialect for test ingestion: {dialect}.")

    values = [
        {
            "project_id": project_id,
            "node_id": node_ids[test_case.identity],
            "class_name": test_case.class_name,
            "name": test_case.name,
        }
        for test_case in parsed_cases
    ]
    persisted_by_node_id = {}
    for offset in range(0, len(values), 5000):
        value_batch = values[offset : offset + 5000]
        node_id_batch = [value["node_id"] for value in value_batch]
        session.execute(
            insert_statement(TestCase)
            .values(value_batch)
            .on_conflict_do_nothing(index_elements=["project_id", "node_id"])
        )
        cases = session.scalars(
            select(TestCase).where(
                TestCase.project_id == project_id,
                TestCase.node_id.in_(node_id_batch),
            )
        )
        persisted_by_node_id.update({test_case.node_id: test_case for test_case in cases})
    return {
        test_case.identity: persisted_by_node_id[node_ids[test_case.identity]].id
        for test_case in parsed_cases
    }


def _run_status(test_cases: Sequence[ParsedTestCase]) -> TestRunStatus:
    if not test_cases:
        return TestRunStatus.EMPTY
    if any(
        test_case.outcome in {TestOutcome.FAILED, TestOutcome.ERROR} for test_case in test_cases
    ):
        return TestRunStatus.FAILED
    return TestRunStatus.COMPLETED


def _node_id(test_case: ParsedTestCase) -> str:
    if len(test_case.name) > 255:
        raise RunIngestionValidationError("Testcase name exceeds the 255-character storage limit.")
    if test_case.class_name is not None and len(test_case.class_name) > 255:
        raise RunIngestionValidationError(
            "Testcase class name exceeds the 255-character storage limit."
        )
    identity = json.dumps(test_case.identity, ensure_ascii=False, separators=(",", ":"))
    return "junit:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _request_fingerprint(
    report_content: bytes, commit_sha: Optional[str], branch: Optional[str]
) -> str:
    digest = hashlib.sha256()
    for value in (report_content, (commit_sha or "").encode(), (branch or "").encode()):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


@dataclass(frozen=True)
class TestRunSummary:
    run: TestRun
    total: int
    passed: int
    failed: int
    skipped: int
    error: int


def list_project_runs(
    session: Session,
    project_id: int,
    *,
    branch: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[TestRun]:
    query = select(TestRun).where(TestRun.project_id == project_id)
    if branch is not None:
        query = query.where(TestRun.branch == branch)
    query = (
        query.order_by(TestRun.ingested_at.desc(), TestRun.id.desc()).limit(limit).offset(offset)
    )
    return list(session.scalars(query))


def count_project_runs(session: Session, project_id: int, *, branch: Optional[str] = None) -> int:
    query = select(func.count()).select_from(TestRun).where(TestRun.project_id == project_id)
    if branch is not None:
        query = query.where(TestRun.branch == branch)
    return session.scalar(query) or 0


def get_project_run(session: Session, project_id: int, run_id: int) -> Optional[TestRun]:
    return session.scalar(
        select(TestRun).where(TestRun.project_id == project_id, TestRun.id == run_id)
    )


def get_project_run_summary(
    session: Session, project_id: int, run_id: int
) -> Optional[TestRunSummary]:
    passed = func.count(TestResult.id).filter(TestResult.outcome == TestOutcome.PASSED)
    failed = func.count(TestResult.id).filter(TestResult.outcome == TestOutcome.FAILED)
    skipped = func.count(TestResult.id).filter(TestResult.outcome == TestOutcome.SKIPPED)
    error = func.count(TestResult.id).filter(TestResult.outcome == TestOutcome.ERROR)
    row = session.execute(
        select(
            TestRun,
            func.count(TestResult.id),
            passed,
            failed,
            skipped,
            error,
        )
        .outerjoin(TestResult, TestResult.test_run_id == TestRun.id)
        .where(TestRun.project_id == project_id, TestRun.id == run_id)
        .group_by(TestRun.id)
    ).one_or_none()
    if row is None:
        return None
    return TestRunSummary(
        run=row[0],
        total=row[1],
        passed=row[2],
        failed=row[3],
        skipped=row[4],
        error=row[5],
    )


def count_run_results(
    session: Session, run_id: int, *, outcome: Optional[TestOutcome] = None
) -> int:
    query = select(func.count()).select_from(TestResult).where(TestResult.test_run_id == run_id)
    if outcome is not None:
        query = query.where(TestResult.outcome == outcome)
    return session.scalar(query) or 0


def list_run_results(
    session: Session,
    run_id: int,
    *,
    outcome: Optional[TestOutcome] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[TestResult]:
    query = (
        select(TestResult)
        .where(TestResult.test_run_id == run_id)
        .options(selectinload(TestResult.test_case))
    )
    if outcome is not None:
        query = query.where(TestResult.outcome == outcome)
    query = query.order_by(TestResult.id.asc()).limit(limit).offset(offset)
    return list(session.scalars(query))
