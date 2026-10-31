from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest
from database import AnalysisJob as AnalysisJobEntity
from database import AnalysisJobStatus, Base
from database import TestRun as RunEntity
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from testpulse.analysis_worker import process_next_analysis_job
from testpulse.app import create_app
from testpulse.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        database_url=URL.create("sqlite", database=str(tmp_path / "analysis-jobs.db")),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as test_client:
        yield test_client


def create_project(client: TestClient) -> int:
    response = client.post("/projects", json={"name": "Analysis jobs"})
    assert response.status_code == 201
    return response.json()["id"]


def upload_run(
    client: TestClient,
    project_id: int,
    *,
    outcome: str = "passed",
    branch: str = "main",
    idempotency_key: Optional[str] = None,
) -> dict:
    failure = (
        '<failure message="assertion failed">expected the operation to succeed</failure>'
        if outcome == "failed"
        else ""
    )
    skipped = '<skipped message="not selected"/>' if outcome == "skipped" else ""
    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=(
            "<testsuite>"
            f'<testcase classname="tests.sample" name="test_operation" time="0.025">'
            f"{failure}{skipped}</testcase>"
            "</testsuite>"
        ),
        headers={
            "Content-Type": "application/xml",
            "X-Branch": branch,
            **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
        },
    )
    assert response.status_code == 201
    return response.json()


def get_job(client: TestClient, project_id: int, run_id: int) -> dict:
    response = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}/analysis-job")
    assert response.status_code == 200
    return response.json()


def test_ingestion_registers_one_pending_job_and_api_works_without_worker(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    run = upload_run(client, project_id)

    job = get_job(client, project_id, run["id"])
    assert job["status"] == "pending"
    assert job["attempts"] == 0
    assert job["max_attempts"] == 3
    assert job["result"] is None
    assert client.get("/projects").status_code == 200
    assert client.get(f"/projects/{project_id}").status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/runs").status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/runs/{run['id']}").status_code == 200


def test_worker_completes_run_analysis_and_persists_regression_snapshot(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    runs = [
        upload_run(client, project_id, outcome="failed" if index == 4 else "passed")
        for index in range(5)
    ]
    engine = client.app.state.database_engine

    for _ in runs:
        assert process_next_analysis_job(engine)
    assert not process_next_analysis_job(engine)

    first_job = get_job(client, project_id, runs[0]["id"])
    assert first_job["status"] == "completed"
    assert first_job["result"]["reliability"][0]["observations"] == 1
    assert first_job["result"]["reliability"][0]["reliability"] == "insufficient_data"

    job = get_job(client, project_id, runs[-1]["id"])
    assert job["status"] == "completed"
    assert job["attempts"] == 1
    assert job["last_error"] is None
    assert job["result"]["previous_run_id"] == runs[-2]["id"]
    assert job["result"]["reliability"] == [
        {
            "test_case_id": runs[-1]["test_results"][0]["test_case_id"],
            "name": "test_operation",
            "class_name": "tests.sample",
            "observations": 5,
            "passed": 4,
            "failed": 1,
            "errors": 0,
            "failure_rate": 0.2,
            "reliability": "potentially_flaky",
            "potentially_flaky": True,
        }
    ]
    assert len(job["result"]["regressions"]) == 1
    assert job["result"]["regressions"][0]["current_outcome"] == "failed"


def test_recoverable_error_retries_then_completes_without_duplicate_job(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    run = upload_run(client, project_id, idempotency_key="retryable-run")
    job_id = get_job(client, project_id, run["id"])["id"]
    calls = 0

    def fail_once(session: Session, claimed_job_id: int) -> dict[str, object]:
        nonlocal calls
        assert claimed_job_id == job_id
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary storage failure")
        return {"processed": True}

    engine = client.app.state.database_engine
    assert process_next_analysis_job(engine, processor=fail_once)
    retried = get_job(client, project_id, run["id"])
    assert retried["status"] == "pending"
    assert retried["attempts"] == 1
    assert retried["last_error"] == "RuntimeError: temporary storage failure"

    assert process_next_analysis_job(engine, processor=fail_once)
    completed = get_job(client, project_id, run["id"])
    assert completed["status"] == "completed"
    assert completed["attempts"] == 2
    assert completed["result"] == {"processed": True}
    assert not process_next_analysis_job(engine, processor=fail_once)
    assert calls == 2

    with Session(engine) as session:
        job_count = session.scalar(
            select(func.count())
            .select_from(AnalysisJobEntity)
            .where(AnalysisJobEntity.test_run_id == run["id"])
        )
    assert job_count == 1


def test_job_is_failed_after_maximum_attempts_and_retains_error(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    run = upload_run(client, project_id)
    engine = client.app.state.database_engine

    def always_fails(session: Session, job_id: int) -> dict[str, object]:
        raise ValueError(f"unrecoverable analysis input {job_id}")

    for _ in range(3):
        assert process_next_analysis_job(engine, processor=always_fails)
    assert not process_next_analysis_job(engine, processor=always_fails)

    job = get_job(client, project_id, run["id"])
    assert job["status"] == "failed"
    assert job["attempts"] == job["max_attempts"] == 3
    assert job["last_error"].startswith("ValueError: unrecoverable analysis input")
    assert job["completed_at"] is not None


def test_pending_job_survives_worker_outage_and_other_database_connection_recovers_it(
    client: TestClient,
    tmp_path: Path,
) -> None:
    project_id = create_project(client)
    run = upload_run(client, project_id)
    job = get_job(client, project_id, run["id"])
    assert job["status"] == "pending"

    worker_engine = create_engine(URL.create("sqlite", database=str(tmp_path / "analysis-jobs.db")))
    try:
        assert process_next_analysis_job(worker_engine)
    finally:
        worker_engine.dispose()

    recovered = get_job(client, project_id, run["id"])
    assert recovered["status"] == "completed"
    assert recovered["attempts"] == 1


def test_invalid_report_does_not_create_run_or_analysis_job(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content="<testsuite><testcase",
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 422

    with Session(client.app.state.database_engine) as session:
        run_count = session.scalar(
            select(func.count()).select_from(RunEntity).where(RunEntity.project_id == project_id)
        )
        job_count = session.scalar(
            select(func.count())
            .select_from(AnalysisJobEntity)
            .where(AnalysisJobEntity.project_id == project_id)
        )
    assert run_count == 0
    assert job_count == 0


def test_empty_run_analysis_completes_with_empty_snapshot(client: TestClient) -> None:
    project_id = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content="<testsuite/>",
        headers={"Content-Type": "application/xml", "X-Branch": "main"},
    )
    assert response.status_code == 201
    run = response.json()

    assert process_next_analysis_job(client.app.state.database_engine)
    job = get_job(client, project_id, run["id"])
    assert job["status"] == "completed"
    assert job["result"]["reliability"] == []
    assert job["result"]["regressions"] == []


def test_expired_worker_lease_recovers_a_crashed_processing_job(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    run = upload_run(client, project_id)
    engine = client.app.state.database_engine
    job = get_job(client, project_id, run["id"])
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    with Session(engine) as session:
        stored_job = session.get(AnalysisJobEntity, job["id"])
        assert stored_job is not None
        stored_job.status = AnalysisJobStatus.PROCESSING
        stored_job.attempts = 1
        stored_job.started_at = expired_at
        stored_job.lease_expires_at = expired_at
        session.commit()

    assert process_next_analysis_job(engine)
    recovered = get_job(client, project_id, run["id"])
    assert recovered["status"] == "completed"
    assert recovered["attempts"] == 2


def test_idempotent_ingestion_does_not_create_another_job(client: TestClient) -> None:
    project_id = create_project(client)
    first = upload_run(client, project_id, idempotency_key="same-report")
    retry = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=(
            "<testsuite>"
            '<testcase classname="tests.sample" name="test_operation" time="0.025"></testcase>'
            "</testsuite>"
        ),
        headers={
            "Content-Type": "application/xml",
            "X-Branch": "main",
            "Idempotency-Key": "same-report",
        },
    )
    assert retry.status_code == 200
    assert retry.json()["id"] == first["id"]

    with Session(client.app.state.database_engine) as session:
        jobs = session.scalars(
            select(AnalysisJobEntity).where(AnalysisJobEntity.test_run_id == first["id"])
        ).all()
    assert len(jobs) == 1
