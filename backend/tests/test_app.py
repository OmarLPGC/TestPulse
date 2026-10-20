from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from testpulse.app import create_app
from testpulse.config import Settings


def test_health_endpoint_starts_api() -> None:
    settings = Settings(
        app_env="test",
        database_url=URL.create("sqlite", database=":memory:"),
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
