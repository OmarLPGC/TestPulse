from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_support import create_authenticated_test_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app, _ = create_authenticated_test_app(tmp_path / "ingestion-tokens.db")
    with TestClient(app) as test_client:
        yield test_client


def create_project(client: TestClient) -> int:
    response = client.post("/projects", json={"name": "Token test project"})
    assert response.status_code == 201
    return response.json()["id"]


def test_create_ingestion_token_returns_name_and_one_time_secret(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/ingestion-tokens",
        json={"name": "  GitHub Actions  "},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "GitHub Actions"
    assert created["token"]

    listed = client.get(f"/api/v1/projects/{project_id}/ingestion-tokens")
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": created["id"],
            "project_id": project_id,
            "name": "GitHub Actions",
            "created_at": created["created_at"],
            "expires_at": None,
            "revoked_at": None,
            "last_used_at": None,
        }
    ]
    assert "token" not in listed.json()[0]


def test_create_ingestion_token_keeps_unnamed_client_compatibility(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.post(f"/api/v1/projects/{project_id}/ingestion-tokens", json={})

    assert response.status_code == 201
    assert response.json()["name"] == "Ingestion token"


@pytest.mark.parametrize("name", ["", " ", " \t\n "])
def test_create_ingestion_token_rejects_empty_name(client: TestClient, name: str) -> None:
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/ingestion-tokens",
        json={"name": name},
    )

    assert response.status_code == 422
