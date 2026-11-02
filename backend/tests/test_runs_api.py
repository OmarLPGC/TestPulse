from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from database import ProjectIngestionToken
from database import TestResult as ResultEntity
from database import TestRun as RunEntity
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_support import create_authenticated_test_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app, _ = create_authenticated_test_app(
        tmp_path / "runs.db",
        max_junit_report_bytes=1024,
        max_junit_test_cases=5,
    )
    with TestClient(app) as test_client:
        test_client.app.state.test_ingestion_tokens = {}
        yield test_client


def create_project(client: TestClient, name: str = "Ingestion") -> int:
    response = client.post("/projects", json={"name": name})
    assert response.status_code == 201
    project_id = response.json()["id"]
    token_response = client.post(f"/api/v1/projects/{project_id}/ingestion-tokens", json={})
    assert token_response.status_code == 201
    token = token_response.json()["token"]
    client.app.state.test_ingestion_tokens[project_id] = token
    client.headers["Authorization"] = f"Bearer {token}"
    return project_id


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


def upload_run(
    client: TestClient,
    project_id: int,
    report: str,
    *,
    branch: str = "main",
) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=report,
        headers={
            "Authorization": f"Bearer {client.app.state.test_ingestion_tokens[project_id]}",
            "Content-Type": "application/xml",
            "X-Branch": branch,
        },
    )
    assert response.status_code == 201
    return response.json()


def set_run_time(client: TestClient, run_id: int, ingested_at: datetime) -> None:
    with Session(client.app.state.database_engine) as session:
        run = session.get(RunEntity, run_id)
        assert run is not None
        run.ingested_at = ingested_at
        session.commit()


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


def test_ingestion_tokens_are_project_scoped_hashed_and_revocable(client: TestClient) -> None:
    project_id = create_project(client)
    other_project_id = create_project(client, "Other ingestion project")
    token = client.app.state.test_ingestion_tokens[project_id]
    with Session(client.app.state.database_engine) as session:
        token_hash = session.scalar(
            select(ProjectIngestionToken.token_hash).where(
                ProjectIngestionToken.project_id == project_id
            )
        )
    assert token_hash != token

    other_project_response = client.post(
        f"/api/v1/projects/{other_project_id}/runs",
        content='<testsuite><testcase name="wrong-project"/></testsuite>',
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/xml"},
    )
    assert other_project_response.status_code == 401
    assert run_counts(client, other_project_id) == (0, 0)

    listed = client.get(f"/api/v1/projects/{project_id}/ingestion-tokens")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert "token" not in listed.json()[0]

    token_id = listed.json()[0]["id"]
    revoked = client.delete(f"/api/v1/projects/{project_id}/ingestion-tokens/{token_id}")
    assert revoked.status_code == 204
    response = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content='<testsuite><testcase name="revoked"/></testsuite>',
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/xml"},
    )
    assert response.status_code == 401
    assert run_counts(client, project_id) == (0, 0)


def test_ci_metadata_is_persisted_and_part_of_idempotency_fingerprint(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    token = client.app.state.test_ingestion_tokens[project_id]
    report = '<testsuite><testcase name="ci-metadata"/></testsuite>'
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/xml",
        "Idempotency-Key": "ci-run-key",
        "X-CI-Source": "github-actions",
        "X-CI-Run-ID": "987654",
        "X-CI-Run-Attempt": "2",
        "X-CI-Event": "pull_request",
        "X-CI-Pull-Request": "17",
    }

    created = client.post(f"/api/v1/projects/{project_id}/runs", content=report, headers=headers)
    repeated = client.post(f"/api/v1/projects/{project_id}/runs", content=report, headers=headers)
    changed_metadata = client.post(
        f"/api/v1/projects/{project_id}/runs",
        content=report,
        headers={**headers, "X-CI-Pull-Request": "18"},
    )

    assert created.status_code == 201
    assert created.json()["ci_source"] == "github-actions"
    assert created.json()["ci_run_id"] == "987654"
    assert created.json()["ci_run_attempt"] == "2"
    assert created.json()["ci_event"] == "pull_request"
    assert created.json()["ci_pull_request"] == "17"
    assert repeated.status_code == 200
    assert changed_metadata.status_code == 409
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


def test_unknown_project_without_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects/999999/runs",
        content="<testsuite/>",
        headers={"Content-Type": "application/xml"},
    )

    assert response.status_code == 401


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


def test_reliability_api_reports_mixed_history_and_branch_filter(client: TestClient) -> None:
    project_id = create_project(client)
    for index, outcome in enumerate(["passed", "passed", "passed", "passed", "failed"]):
        outcome_xml = '<failure message="failure"/>' if outcome == "failed" else ""
        run = upload_run(
            client,
            project_id,
            f'<testsuite><testcase classname="sample.Case" name="flaky">{outcome_xml}'
            "</testcase></testsuite>",
            branch="main",
        )
        set_run_time(
            client,
            run["id"],
            datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
        )
    upload_run(
        client,
        project_id,
        '<testsuite><testcase classname="other.Case" name="only-other-branch"/></testsuite>',
        branch="release",
    )

    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/reliability",
        params={"branch": "main", "window_size": 5},
    )

    assert response.status_code == 200
    assert response.json()["window_size"] == 5
    assert response.json()["minimum_observations"] == 5
    assert len(response.json()["tests"]) == 1
    assert response.json()["tests"][0]["reliability"] == "potentially_flaky"
    assert response.json()["tests"][0]["failure_rate"] == 0.2
    assert response.json()["tests"][0]["potentially_flaky"] is True


def test_reliability_api_rejects_invalid_window_and_unknown_project(
    client: TestClient,
) -> None:
    project_id = create_project(client)

    invalid_window = client.get(
        f"/api/v1/projects/{project_id}/analysis/reliability",
        params={"window_size": 101},
    )
    unknown_project = client.get("/api/v1/projects/999999/analysis/reliability")

    assert invalid_window.status_code == 422
    assert unknown_project.status_code == 404


def test_reliability_api_excludes_skipped_from_minimum_and_defaults(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    for index in range(4):
        run = upload_run(
            client,
            project_id,
            '<testsuite><testcase classname="sample.Case" name="not-enough"/></testsuite>',
        )
        set_run_time(
            client,
            run["id"],
            datetime(2025, 2, 1, tzinfo=timezone.utc) + timedelta(days=index),
        )
    skipped = upload_run(
        client,
        project_id,
        '<testsuite><testcase classname="sample.Case" name="not-enough">'
        "<skipped/></testcase></testsuite>",
    )
    set_run_time(client, skipped["id"], datetime(2025, 2, 5, tzinfo=timezone.utc))

    response = client.get(f"/api/v1/projects/{project_id}/analysis/reliability")

    assert response.status_code == 200
    assert response.json()["window_size"] == 20
    assert response.json()["minimum_observations"] == 5
    test_result = response.json()["tests"][0]
    assert test_result["observations"] == 4
    assert test_result["reliability"] == "insufficient_data"


def test_reliability_api_limits_history_to_latest_valid_observations(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    older_failure = upload_run(
        client,
        project_id,
        '<testsuite><testcase classname="sample.Case" name="windowed">'
        "<failure/></testcase></testsuite>",
    )
    set_run_time(client, older_failure["id"], datetime(2025, 3, 1, tzinfo=timezone.utc))
    for index in range(20):
        run = upload_run(
            client,
            project_id,
            '<testsuite><testcase classname="sample.Case" name="windowed"/></testsuite>',
        )
        set_run_time(
            client,
            run["id"],
            datetime(2025, 3, 2, tzinfo=timezone.utc) + timedelta(days=index),
        )

    response = client.get(
        f"/api/v1/projects/{project_id}/analysis/reliability",
        params={"window_size": 20},
    )

    assert response.status_code == 200
    test_result = response.json()["tests"][0]
    assert test_result["observations"] == 20
    assert test_result["failed"] == 0
    assert test_result["failure_rate"] == 0
    assert test_result["reliability"] == "stable"


def test_regression_api_detects_only_new_pass_to_failure_changes(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    previous = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase classname="sample.Case" name="regression"/>'
        '<testcase classname="sample.Case" name="persistent"><failure/></testcase>'
        '<testcase classname="sample.Case" name="still-passing"/>'
        "</testsuite>",
    )
    current = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase classname="sample.Case" name="regression"><failure/></testcase>'
        '<testcase classname="sample.Case" name="persistent"><failure/></testcase>'
        '<testcase classname="sample.Case" name="still-passing"/>'
        '<testcase classname="sample.Case" name="new-failure"><failure/></testcase>'
        "</testsuite>",
    )
    set_run_time(client, previous["id"], datetime(2025, 1, 1, tzinfo=timezone.utc))
    set_run_time(client, current["id"], datetime(2025, 1, 2, tzinfo=timezone.utc))

    response = client.get(f"/api/v1/projects/{project_id}/runs/{current['id']}/regressions")

    assert response.status_code == 200
    assert response.json()["previous_run_id"] is not None
    assert [item["name"] for item in response.json()["regressions"]] == ["regression"]


def test_regression_api_never_compares_different_branches(client: TestClient) -> None:
    project_id = create_project(client)
    branch_a = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase classname="sample.Case" name="test"><failure/></testcase>'
        "</testsuite>",
        branch="branch-a",
    )
    current = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase classname="sample.Case" name="test"><failure/></testcase>'
        "</testsuite>",
        branch="branch-b",
    )
    set_run_time(client, branch_a["id"], datetime(2025, 1, 1, tzinfo=timezone.utc))
    set_run_time(client, current["id"], datetime(2025, 1, 2, tzinfo=timezone.utc))

    response = client.get(f"/api/v1/projects/{project_id}/runs/{current['id']}/regressions")

    assert response.status_code == 200
    assert response.json()["branch"] == "branch-b"
    assert response.json()["previous_run_id"] is None
    assert response.json()["regressions"] == []


def test_regression_api_uses_previous_run_from_same_branch(client: TestClient) -> None:
    project_id = create_project(client)
    branch_b_previous = upload_run(
        client,
        project_id,
        '<testsuite><testcase classname="sample.Case" name="test"/></testsuite>',
        branch="branch-b",
    )
    branch_a = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase classname="sample.Case" name="test"><failure/></testcase>'
        "</testsuite>",
        branch="branch-a",
    )
    current = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase classname="sample.Case" name="test"><failure/></testcase>'
        "</testsuite>",
        branch="branch-b",
    )
    set_run_time(client, branch_b_previous["id"], datetime(2025, 1, 1, tzinfo=timezone.utc))
    set_run_time(client, branch_a["id"], datetime(2025, 1, 2, tzinfo=timezone.utc))
    set_run_time(client, current["id"], datetime(2025, 1, 3, tzinfo=timezone.utc))

    response = client.get(f"/api/v1/projects/{project_id}/runs/{current['id']}/regressions")

    assert response.status_code == 200
    assert response.json()["previous_run_id"] == branch_b_previous["id"]
    assert [item["name"] for item in response.json()["regressions"]] == ["test"]


def test_regression_api_returns_404_for_missing_run(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.get(f"/api/v1/projects/{project_id}/runs/999999/regressions")

    assert response.status_code == 404


def test_regression_api_returns_empty_list_when_no_regressions_exist(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    previous = upload_run(
        client,
        project_id,
        '<testsuite><testcase classname="sample.Case" name="passing"/></testsuite>',
    )
    current = upload_run(
        client,
        project_id,
        '<testsuite><testcase classname="sample.Case" name="passing"/></testsuite>',
    )
    set_run_time(client, previous["id"], datetime(2025, 1, 1, tzinfo=timezone.utc))
    set_run_time(client, current["id"], datetime(2025, 1, 2, tzinfo=timezone.utc))

    response = client.get(f"/api/v1/projects/{project_id}/runs/{current['id']}/regressions")

    assert response.status_code == 200
    assert response.json()["previous_run_id"] == previous["id"]
    assert response.json()["regressions"] == []


def test_run_history_is_newest_first_and_filters_by_branch(client: TestClient) -> None:
    project_id = create_project(client)
    first = upload_run(client, project_id, '<testsuite><testcase name="first"/></testsuite>')
    second = upload_run(
        client,
        project_id,
        '<testsuite><testcase name="second"/></testsuite>',
        branch="release",
    )
    third = upload_run(client, project_id, '<testsuite><testcase name="third"/></testsuite>')

    with Session(client.app.state.database_engine) as session:
        tied_ingestion_time = datetime(2025, 1, 2, tzinfo=timezone.utc)
        session.get(RunEntity, first["id"]).ingested_at = tied_ingestion_time
        session.get(RunEntity, second["id"]).ingested_at = tied_ingestion_time
        session.get(RunEntity, third["id"]).ingested_at = datetime(2025, 1, 3, tzinfo=timezone.utc)
        session.commit()

    response = client.get(f"/api/v1/projects/{project_id}/runs")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        third["id"],
        second["id"],
        first["id"],
    ]
    assert response.json()["total"] == 3
    assert all("test_results" not in item for item in response.json()["items"])

    filtered = client.get(f"/api/v1/projects/{project_id}/runs", params={"branch": "main"})

    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [third["id"], first["id"]]
    assert filtered.json()["total"] == 2


def test_run_history_pagination_has_no_duplicates(client: TestClient) -> None:
    project_id = create_project(client)
    runs = [
        upload_run(
            client,
            project_id,
            f'<testsuite><testcase name="case-{index}"/></testsuite>',
        )
        for index in range(5)
    ]

    first_page = client.get(f"/api/v1/projects/{project_id}/runs", params={"limit": 2, "offset": 0})
    second_page = client.get(
        f"/api/v1/projects/{project_id}/runs", params={"limit": 2, "offset": 2}
    )
    third_page = client.get(f"/api/v1/projects/{project_id}/runs", params={"limit": 2, "offset": 4})

    assert first_page.status_code == second_page.status_code == third_page.status_code == 200
    first_ids = [item["id"] for item in first_page.json()["items"]]
    second_ids = [item["id"] for item in second_page.json()["items"]]
    third_ids = [item["id"] for item in third_page.json()["items"]]
    assert len(first_ids) == len(second_ids) == 2
    assert len(third_ids) == 1
    assert set(first_ids).isdisjoint(second_ids)
    assert set(first_ids + second_ids).isdisjoint(third_ids)
    assert set(first_ids + second_ids + third_ids) == {run["id"] for run in runs}


@pytest.mark.parametrize("params", [{"limit": 101}, {"limit": 0}, {"offset": -1}])
def test_history_rejects_invalid_pagination(client: TestClient, params: dict[str, int]) -> None:
    project_id = create_project(client)

    response = client.get(f"/api/v1/projects/{project_id}/runs", params=params)

    assert response.status_code == 422


def test_run_details_return_sql_result_counts(client: TestClient) -> None:
    project_id = create_project(client)
    run = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase name="passed"/>'
        '<testcase name="failed"><failure/></testcase>'
        '<testcase name="skipped"><skipped/></testcase>'
        '<testcase name="errored"><error/></testcase>'
        "</testsuite>",
    )

    response = client.get(f"/api/v1/projects/{project_id}/runs/{run['id']}")

    assert response.status_code == 200
    assert {
        key: response.json()[key] for key in ("total", "passed", "failed", "skipped", "error")
    } == {"total": 4, "passed": 1, "failed": 1, "skipped": 1, "error": 1}
    assert response.json()["ingested_at"]
    assert "test_results" not in response.json()


def test_run_results_filter_by_status_and_paginate(client: TestClient) -> None:
    project_id = create_project(client)
    run = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase name="passed"/>'
        '<testcase name="failed"><failure/></testcase>'
        '<testcase name="failed-again"><failure/></testcase>'
        '<testcase name="skipped"><skipped/></testcase>'
        "</testsuite>",
    )

    response = client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}/results",
        params={"status": "failed", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["limit"] == 1
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["outcome"] == "failed"

    invalid_status = client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}/results",
        params={"status": "completed"},
    )
    assert invalid_status.status_code == 422


def test_run_results_pagination_uses_stable_result_order(client: TestClient) -> None:
    project_id = create_project(client)
    run = upload_run(
        client,
        project_id,
        "<testsuite>"
        '<testcase name="first"/>'
        '<testcase name="second"/>'
        '<testcase name="third"/>'
        "</testsuite>",
    )

    first_page = client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}/results",
        params={"limit": 2, "offset": 0},
    )
    second_page = client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}/results",
        params={"limit": 2, "offset": 2},
    )

    assert first_page.status_code == second_page.status_code == 200
    first_ids = [item["id"] for item in first_page.json()["items"]]
    second_ids = [item["id"] for item in second_page.json()["items"]]
    assert len(first_ids) == 2
    assert len(second_ids) == 1
    assert set(first_ids).isdisjoint(second_ids)
    assert first_page.json()["total"] == second_page.json()["total"] == 3


@pytest.mark.parametrize("params", [{"limit": 101}, {"limit": 0}, {"offset": -1}])
def test_run_results_reject_invalid_pagination(client: TestClient, params: dict[str, int]) -> None:
    project_id = create_project(client)
    run = upload_run(client, project_id, '<testsuite><testcase name="case"/></testsuite>')

    response = client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}/results",
        params=params,
    )

    assert response.status_code == 422


def test_run_detail_and_results_return_404_for_missing_or_foreign_run(
    client: TestClient,
) -> None:
    project_id = create_project(client, "Owner")
    other_project_id = create_project(client, "Other")
    run = upload_run(client, project_id, '<testsuite><testcase name="ok"/></testsuite>')

    missing_detail = client.get(f"/api/v1/projects/{project_id}/runs/999999")
    foreign_detail = client.get(f"/api/v1/projects/{other_project_id}/runs/{run['id']}")
    missing_results = client.get(f"/api/v1/projects/{project_id}/runs/999999/results")
    foreign_results = client.get(f"/api/v1/projects/{other_project_id}/runs/{run['id']}/results")
    missing_project = client.get("/api/v1/projects/999999/runs")

    assert [
        missing_detail.status_code,
        foreign_detail.status_code,
        missing_results.status_code,
        foreign_results.status_code,
        missing_project.status_code,
    ] == [404, 404, 404, 404, 404]
