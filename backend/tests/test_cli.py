from collections.abc import Iterator
from pathlib import Path
from typing import Callable

import httpx
import pytest
from database import Base
from database import TestRun as RunEntity
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from testpulse.app import create_app
from testpulse.cli import main
from testpulse.config import Settings


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        database_url=URL.create("sqlite", database=str(tmp_path / "cli.db")),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database_engine)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def project_id(api_client: TestClient) -> int:
    response = api_client.post("/projects", json={"name": "CLI integration"})
    assert response.status_code == 201
    return response.json()["id"]


def api_client_factory(
    api_client: TestClient,
) -> Callable[..., httpx.Client]:
    def factory(**kwargs: object) -> httpx.Client:
        def handle_request(request: httpx.Request) -> httpx.Response:
            response = api_client.request(
                request.method,
                str(request.url),
                content=request.content,
                headers=dict(request.headers),
            )
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=response.content,
                request=request,
            )

        return httpx.Client(transport=httpx.MockTransport(handle_request), **kwargs)

    return factory


def test_cli_uploads_report_to_test_api_and_preserves_metadata(
    api_client: TestClient,
    project_id: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "junit.xml"
    report_path.write_text(
        '<testsuite><testcase classname="sample.Test" name="passes"/></testsuite>',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--url",
            "http://testpulse.example/",
            "--project",
            str(project_id),
            "--report",
            str(report_path),
            "--commit",
            "abc123",
            "--branch",
            "feature/cli",
            "--idempotency-key",
            "cli-run-1",
        ],
        client_factory=api_client_factory(api_client),
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert "Ejecución creada correctamente" in output.out
    history = api_client.get(f"/api/v1/projects/{project_id}/runs").json()
    assert len(history["items"]) == 1
    assert history["items"][0]["commit_sha"] == "abc123"
    assert history["items"][0]["branch"] == "feature/cli"


def test_cli_reports_missing_report_without_network_request(
    project_id: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--url",
            "http://testpulse.example",
            "--project",
            str(project_id),
            "--report",
            str(tmp_path / "missing.xml"),
        ]
    )

    output = capsys.readouterr()
    assert exit_code != 0
    assert "no se pudo leer el informe" in output.err
    assert "Traceback" not in output.err


def test_cli_reports_network_failure_without_traceback(
    project_id: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "junit.xml"
    report_path.write_text("<testsuite/>", encoding="utf-8")

    def unavailable_client(**kwargs: object) -> httpx.Client:
        def fail_request(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        return httpx.Client(transport=httpx.MockTransport(fail_request), **kwargs)

    exit_code = main(
        [
            "--url",
            "http://unavailable.example",
            "--project",
            str(project_id),
            "--report",
            str(report_path),
        ],
        client_factory=unavailable_client,
    )

    output = capsys.readouterr()
    assert exit_code != 0
    assert "Error de red" in output.err
    assert "Traceback" not in output.err


def test_cli_rejects_invalid_url_without_traceback(
    project_id: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "junit.xml"
    report_path.write_text("<testsuite/>", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--url",
                "ftp://testpulse.example",
                "--project",
                str(project_id),
                "--report",
                str(report_path),
            ]
        )

    output = capsys.readouterr()
    assert error.value.code == 2
    assert "http://" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize(
    ("status_code", "response_body", "expected_message"),
    [
        (401, {"detail": "Unauthorized"}, "Autenticación rechazada"),
        (422, {"detail": "JUnit XML is malformed."}, "JUnit XML is malformed."),
        (500, {"detail": "internal stack trace"}, "error del servidor"),
    ],
)
def test_cli_http_errors_never_report_success(
    project_id: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status_code: int,
    response_body: dict[str, str],
    expected_message: str,
) -> None:
    report_path = tmp_path / "junit.xml"
    report_path.write_text("<testsuite/>", encoding="utf-8")

    def error_client(**kwargs: object) -> httpx.Client:
        def reject_request(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json=response_body, request=request)

        return httpx.Client(transport=httpx.MockTransport(reject_request), **kwargs)

    exit_code = main(
        [
            "--url",
            "http://testpulse.example",
            "--project",
            str(project_id),
            "--report",
            str(report_path),
            "--token",
            "secret-token",
        ],
        client_factory=error_client,
    )

    output = capsys.readouterr()
    assert exit_code != 0
    assert expected_message in output.err
    assert "internal stack trace" not in output.err
    assert "secret-token" not in output.err
    assert "correctamente" not in output.out


def test_cli_reuses_explicit_idempotency_key_without_duplicating_run(
    api_client: TestClient,
    project_id: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "junit.xml"
    report_path.write_text(
        '<testsuite><testcase name="passes"/></testsuite>',
        encoding="utf-8",
    )
    args = [
        "--url",
        "http://testpulse.example",
        "--project",
        str(project_id),
        "--report",
        str(report_path),
        "--commit",
        "abc123",
        "--branch",
        "main",
        "--idempotency-key",
        "github-actions:run-123:1",
    ]
    client_factory = api_client_factory(api_client)

    assert main(args, client_factory=client_factory) == 0
    assert main(args, client_factory=client_factory) == 0

    output = capsys.readouterr()
    assert "Ejecución reutilizada correctamente" in output.out
    with Session(api_client.app.state.database_engine) as session:
        run_count = session.scalar(
            select(func.count()).select_from(RunEntity).where(RunEntity.project_id == project_id)
        )
    assert run_count == 1


def test_cli_generates_stable_idempotency_key_for_github_attempt(
    api_client: TestClient,
    project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/service")
    monkeypatch.setenv("GITHUB_RUN_ID", "987654")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    report_path = tmp_path / "junit.xml"
    report_path.write_text("<testsuite/>", encoding="utf-8")
    captured_headers: list[dict[str, str]] = []

    def capturing_client(**kwargs: object) -> httpx.Client:
        def capture_request(request: httpx.Request) -> httpx.Response:
            captured_headers.append(dict(request.headers))
            response = api_client.request(
                request.method,
                str(request.url),
                content=request.content,
                headers=dict(request.headers),
            )
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=response.content,
                request=request,
            )

        return httpx.Client(transport=httpx.MockTransport(capture_request), **kwargs)

    exit_code = main(
        [
            "--url",
            "http://testpulse.example",
            "--project",
            str(project_id),
            "--report",
            str(report_path),
        ],
        client_factory=capturing_client,
    )

    assert exit_code == 0
    assert captured_headers[0]["idempotency-key"] == (
        f"github-actions:example/service:987654:2:{project_id}"
    )
