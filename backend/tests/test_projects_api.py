from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_support import create_authenticated_test_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app, _ = create_authenticated_test_app(tmp_path / "projects.db")
    with TestClient(app) as test_client:
        yield test_client


def test_create_project_returns_created_project(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json={"name": "TestPulse", "repository_url": "https://github.com/example/testpulse"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "TestPulse"
    assert response.json()["repository_url"] == "https://github.com/example/testpulse"
    assert isinstance(response.json()["id"], int)
    assert response.json()["created_at"]
    assert response.json()["updated_at"]


def test_create_project_trims_name(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "  TestPulse  "})

    assert response.status_code == 201
    assert response.json()["name"] == "TestPulse"


@pytest.mark.parametrize("name", ["", " ", " \t\n "])
def test_create_project_rejects_empty_or_whitespace_name(client: TestClient, name: str) -> None:
    response = client.post("/projects", json={"name": name})

    assert response.status_code == 422


def test_create_project_rejects_invalid_repository_url(client: TestClient) -> None:
    response = client.post("/projects", json={"name": "TestPulse", "repository_url": "not-a-url"})

    assert response.status_code == 422


def test_create_project_rejects_duplicate_name(client: TestClient) -> None:
    first = client.post("/projects", json={"name": "TestPulse"})
    duplicate = client.post("/projects", json={"name": "TestPulse"})

    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_list_projects_returns_created_projects(client: TestClient) -> None:
    client.post("/projects", json={"name": "Project one"})
    client.post("/projects", json={"name": "Project two"})

    response = client.get("/projects")

    assert response.status_code == 200
    assert [project["name"] for project in response.json()] == ["Project one", "Project two"]


def test_get_unknown_project_returns_not_found(client: TestClient) -> None:
    response = client.get("/projects/999999")

    assert response.status_code == 404
