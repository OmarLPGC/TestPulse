from collections.abc import Iterator
from pathlib import Path

import pytest
from database import Base
from database import TestResult as ResultEntity
from database import TestRun as RunEntity
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from testpulse.app import create_app
from testpulse.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        database_url=URL.create("sqlite", database=str(tmp_path / "runs.db")),
        max_junit_report_bytes=1024,
        max_junit_test_cases=5,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as test_client:
        yield test_client


def create_project(client: TestClient, name: str = "Ingestion") -> int:
    response = client.post("/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def run_counts(client: TestClient, project_id: int) -> tuple[int, int]:
    engine = client.app.state.database_engine
    with Session(engine) as session:
        runs = session.scalar(
            select(func.count()).select_from(RunEntity).where(RunEntity.project_id == project_id)
        )
        results = session.scalar(
            select(func.count())
            .select_from(ResultEntity)
            .where(ResultEntity.project_id == project_id)
        )
    return runs or 0, results or 0


def test_ingests_report_and_persists_results_with_metadata(client: TestClient) -> None:
    project_id = create_project(client)
    report = (
        "<testsuite tests='999' failures='0'>"
        '<testcase classname="sample.Case" name="passes" time="0.125"/>'
        '<testcase classname="sample.Case" name="fails">'
        '<failure message="assertion failed">expected one</failure>'
        "</testcase>"
        '<testcase classname="sample.Case" name="errors">'
        '<error message="unexpected">stack trace</error>'
        "</testcase>"
        '<testcase classname="sample.Case" name="skips"><skipped/></testcase>'
        "</testsuite>"
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=report,
        headers={
            "Content-Type": "application/xml",
            "X-Commit-SHA": "abc123",
            "X-Branch": "feature/parser",
        },
    )

    assert response.status_code == 201
    run = response.json()
    assert run["project_id"] == project_id
    assert run["commit_sha"] == "abc123"
    assert run["branch"] == "feature/parser"
    assert run["status"] == "failed"
    assert len(run["test_results"]) == 4
    assert {item["outcome"] for item in run["test_results"]} == {
        "passed",
        "failed",
        "error",
        "skipped",
    }
    failure = next(item for item in run["test_results"] if item["outcome"] == "failed")
    assert failure["error_message"] == "assertion failed"
    assert failure["traceback"] == "expected one"
    assert run_counts(client, project_id) == (1, 4)


def test_idempotent_retries_return_existing_run(client: TestClient) -> None:
    project_id = create_project(client)
    report = '<testsuite><testcase name="passes"/></testsuite>'
    request_headers = {
        "Content-Type": "application/xml",
        "X-Commit-SHA": "abc123",
        "X-Branch": "main",
        "Idempotency-Key": "build-123",
    }

    first = client.post(
        f"/api/v1/projects/{project_id}/runs", content=report, headers=request_headers
    )
    retry = client.post(
        f"/api/v1/projects/{project_id}/runs", content=report, headers=request_headers
    )

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert run_counts(client, project_id) == (1, 1)


@pytest.mark.parametrize(
    ("report", "headers"),
    [
        (
            '<testsuite><testcase name="different"/></testsuite>',
            {"Content-Type": "application/xml", "Idempotency-Key": "key"},
        ),
        (
            '<testsuite><testcase name="same"/></testsuite>',
            {
                "Content-Type": "application/xml",
                "Idempotency-Key": "key",
                "X-Branch": "different",
            },
        ),
    ],
    ids=["different-content", "different-metadata"],
)
def test_idempotency_key_conflicts_on_changed_request(
    client: TestClient, report: str, headers: dict[str, str]
) -> None:
    project_id = create_project(client)
    original_report = '<testsuite><testcase name="same"/></testsuite>'
    client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=original_report,
        headers={"Content-Type": "application/xml", "Idempotency-Key": "key"},
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=report,
        headers=headers,
    )

    assert response.status_code == 409
    assert run_counts(client, project_id) == (1, 1)


def test_invalid_report_is_rejected_without_persisting_anything(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content="<testsuite><testcase>",
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 422
    assert run_counts(client, project_id) == (0, 0)


def test_oversized_report_returns_413(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content="x" * 1025,
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 413
    assert run_counts(client, project_id) == (0, 0)


def test_unknown_project_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects/999999/runs",
        content="<testsuite/>",
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 404


def test_empty_report_is_persisted_with_empty_status(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content="<testsuites><testsuite tests='100'/></testsuites>",
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "empty"
    assert response.json()["test_results"] == []
    assert run_counts(client, project_id) == (1, 0)


def test_configured_test_case_limit_is_enforced(client: TestClient) -> None:
    project_id = create_project(client)
    report = (
        "<testsuite>"
        '<testcase name="one"/>'
        '<testcase name="two"/>'
        '<testcase name="three"/>'
        '<testcase name="four"/>'
        '<testcase name="five"/>'
        '<testcase name="six"/>'
        "</testsuite>"
    )

    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=report,
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 422
    assert run_counts(client, project_id) == (0, 0)
