import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from api.dependencies import get_github_client
from database import Base, User, UserSession, Workspace, WorkspaceMembership
from database.schemas.project_entity import Project
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from testpulse.app import create_app
from testpulse.config import Settings
from testpulse.github_app import GitHubCredentials, GitHubError
from testpulse.token_crypto import decrypt_token, encrypt_token

GITHUB_ACCESS_TOKEN = "github-access-token-for-tests"
GITHUB_ENCRYPTION_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"


class FakeGitHubClient:
    def authorization_url(self, callback_url: str, state: str) -> str:
        return "https://github.com/login/oauth/authorize?" + (
            f"client_id=test-client&redirect_uri={callback_url}&state={state}"
        )

    def exchange_code(self, code: str) -> GitHubCredentials:
        assert code == "test-code"
        return GitHubCredentials(
            access_token=GITHUB_ACCESS_TOKEN,
            refresh_token="github-refresh-token-for-tests",
            expires_in=3600,
        )

    def refresh_credentials(self, refresh_token: str) -> GitHubCredentials:
        assert refresh_token == "github-refresh-token-for-tests"
        return GitHubCredentials(
            access_token="refreshed-github-access-token",
            refresh_token="rotated-refresh-token",
            expires_in=3600,
        )

    def get_authenticated_user(self, access_token: str) -> dict[str, object]:
        assert access_token == GITHUB_ACCESS_TOKEN
        return {
            "id": 123456,
            "login": "test-user",
            "name": "Test User",
            "avatar_url": "https://avatars.example.test/test-user",
        }

    def list_repositories(
        self, access_token: str, *, page: int, per_page: int
    ) -> tuple[list[dict[str, object]], bool]:
        assert access_token in {
            GITHUB_ACCESS_TOKEN,
            "refreshed-github-access-token",
        }
        assert page == 2
        assert per_page == 10
        return (
            [
                {
                    "id": 9001,
                    "full_name": "org/private-project",
                    "html_url": "https://github.com/org/private-project",
                    "private": True,
                    "permissions": {"pull": True, "push": False},
                }
            ],
            True,
        )

    def get_repository(self, access_token: str, full_name: str) -> dict[str, object]:
        assert access_token == GITHUB_ACCESS_TOKEN
        assert full_name == "org/private-project"
        return {
            "id": 9001,
            "full_name": full_name,
            "html_url": f"https://github.com/{full_name}",
            "private": True,
            "permissions": {"pull": True, "push": False},
        }


def create_client(database_path: Path) -> TestClient:
    settings = Settings(
        app_env="test",
        database_url=URL.create("sqlite", database=str(database_path)),
        github_app_client_id="test-client",
        github_app_client_secret="test-secret",
        github_app_callback_url="http://testserver/api/v1/auth/github/callback",
        public_base_url="http://testserver",
        github_token_encryption_key=GITHUB_ENCRYPTION_KEY,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database_engine)
    app.dependency_overrides[get_github_client] = lambda: FakeGitHubClient()
    return TestClient(app, follow_redirects=False)


def complete_login(client: TestClient) -> tuple[dict[str, object], str]:
    login = client.get("/api/v1/auth/github/login")
    assert login.status_code == 302
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "test-code", "state": state},
    )
    assert callback.status_code == 303
    assert "testpulse_session=" in callback.headers["set-cookie"]
    user_response = client.get("/api/v1/auth/me")
    assert user_response.status_code == 200
    return user_response.json(), state


def test_github_login_creates_encrypted_revocable_session_and_personal_workspace(
    tmp_path: Path,
) -> None:
    with create_client(tmp_path / "auth.db") as client:
        identity, state = complete_login(client)

        assert identity["github_user_id"] == 123456
        assert identity["github_login"] == "test-user"
        assert "github-access-token-for-tests" not in str(identity)
        workspaces = client.get("/api/v1/workspaces")
        assert workspaces.status_code == 200
        assert len(workspaces.json()) == 1
        assert workspaces.json()[0]["role"] == "owner"
        assert workspaces.json()[0]["is_personal"] is True

        with Session(client.app.state.database_engine) as session:
            user_session = session.scalar(select(UserSession))
            assert user_session is not None
            assert GITHUB_ACCESS_TOKEN not in user_session.github_access_token_ciphertext
            assert (
                decrypt_token(user_session.github_access_token_ciphertext, GITHUB_ENCRYPTION_KEY)
                == GITHUB_ACCESS_TOKEN
            )

        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": identity["csrf_token"]},
        )
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401
        replay = client.get(
            "/api/v1/auth/github/callback",
            params={"code": "test-code", "state": state},
        )
        assert replay.status_code == 400


def test_corrupt_encrypted_github_token_raises_value_error() -> None:
    with pytest.raises(ValueError, match="could not be decrypted"):
        decrypt_token("A" * 64, GITHUB_ENCRYPTION_KEY)


def test_github_oauth_error_code_is_available_without_exposing_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testpulse.github_app import GitHubAppClient

    def reject_token_exchange(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": "incorrect_client_credentials",
                "error_description": "sensitive provider response",
            },
        )

    monkeypatch.setattr(httpx, "post", reject_token_exchange)
    client = GitHubAppClient("client-id", "client-secret")

    with pytest.raises(GitHubError) as error:
        client.exchange_code("authorization-code")

    assert error.value.provider_error == "incorrect_client_credentials"
    assert "sensitive provider response" not in str(error.value)


def test_authentication_and_csrf_are_required_for_private_routes(tmp_path: Path) -> None:
    with create_client(tmp_path / "auth-required.db") as client:
        assert client.get("/projects").status_code == 401
        identity, _ = complete_login(client)
        assert client.post("/projects", json={"name": "Missing CSRF"}).status_code == 403
        created = client.post(
            "/projects",
            json={"name": "CSRF protected"},
            headers={"X-CSRF-Token": identity["csrf_token"]},
        )
        assert created.status_code == 201


def test_oauth_state_is_bound_to_browser_cookie(tmp_path: Path) -> None:
    with create_client(tmp_path / "oauth-state.db") as client:
        login = client.get("/api/v1/auth/github/login")
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        mismatch = client.get(
            "/api/v1/auth/github/callback",
            params={"code": "test-code", "state": state + "tampered"},
        )
        assert mismatch.status_code == 400
        assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected_and_expired_github_token_refreshes(
    tmp_path: Path,
) -> None:
    with create_client(tmp_path / "session-expiry.db") as client:
        complete_login(client)
        with Session(client.app.state.database_engine) as session:
            user_session = session.scalar(select(UserSession))
            assert user_session is not None
            user_session.github_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()

        repositories = client.get("/api/v1/github/repositories?page=2&per_page=10")
        assert repositories.status_code == 200
        with Session(client.app.state.database_engine) as session:
            user_session = session.scalar(select(UserSession))
            assert user_session is not None
            assert (
                decrypt_token(user_session.github_access_token_ciphertext, GITHUB_ENCRYPTION_KEY)
                == "refreshed-github-access-token"
            )
            user_session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
        assert client.get("/api/v1/auth/me").status_code == 401


def test_github_errors_are_not_exposed_to_api_clients(tmp_path: Path) -> None:
    class FailedAuthorization(FakeGitHubClient):
        def exchange_code(self, code: str) -> GitHubCredentials:
            raise GitHubError(401)

    client = create_client(tmp_path / "github-error.db")
    client.app.dependency_overrides[get_github_client] = lambda: FailedAuthorization()
    with client:
        login = client.get("/api/v1/auth/github/login")
        state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
        callback = client.get(
            "/api/v1/auth/github/callback",
            params={"code": "test-code", "state": state},
        )
        assert callback.status_code == 502
        assert "sensitive provider response" not in callback.text


def test_github_repository_listing_and_workspace_owner_connection(tmp_path: Path) -> None:
    with create_client(tmp_path / "repositories.db") as client:
        identity, _ = complete_login(client)
        page = client.get("/api/v1/github/repositories?page=2&per_page=10")
        assert page.status_code == 200
        assert page.json()["has_next"] is True
        assert page.json()["items"][0]["id"] == 9001

        project = client.post(
            "/projects",
            json={"name": "Repository project"},
            headers={"X-CSRF-Token": identity["csrf_token"]},
        )
        connected = client.post(
            f"/api/v1/projects/{project.json()['id']}/repository",
            json={"github_repository_id": 9001, "full_name": "org/private-project"},
            headers={"X-CSRF-Token": identity["csrf_token"]},
        )
        assert connected.status_code == 200
        assert connected.json()["full_name"] == "org/private-project"
        stored = client.get(f"/projects/{project.json()['id']}")
        assert stored.json()["repository_provider"] == "github"
        assert stored.json()["repository_id"] == 9001


def test_member_can_read_but_cannot_manage_project_or_cross_workspace_data(
    tmp_path: Path,
) -> None:
    with create_client(tmp_path / "workspaces.db") as client:
        identity, _ = complete_login(client)
        project = client.post(
            "/projects",
            json={"name": "Owner project"},
            headers={"X-CSRF-Token": identity["csrf_token"]},
        )
        owner_workspace_id = project.json()["workspace_id"]

        with Session(client.app.state.database_engine) as session:
            owner = session.scalar(select(User).where(User.github_user_id == 123456))
            assert owner is not None
            member = User(github_user_id=654321, github_login="workspace-member")
            other_workspace = Workspace(name="Other workspace")
            session.add_all((member, other_workspace))
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=owner_workspace_id, user_id=member.id, role="member"
                    ),
                    WorkspaceMembership(
                        workspace_id=other_workspace.id, user_id=member.id, role="owner"
                    ),
                ]
            )
            other_project = Project(
                workspace_id=other_workspace.id,
                name="Private project",
            )
            session.add(other_project)
            session.flush()
            other_project_id = other_project.id
            member_session_token = "member-session-token-for-tests"
            session.add(
                UserSession(
                    token_hash=hashlib.sha256(member_session_token.encode()).hexdigest(),
                    user_id=member.id,
                    csrf_token="member-csrf-token",
                    github_access_token_ciphertext=encrypt_token(
                        "member-github-token", GITHUB_ENCRYPTION_KEY
                    ),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            session.commit()

        client.cookies.set("testpulse_session", member_session_token, path="/")
        readable = client.get(f"/projects/{project.json()['id']}")
        hidden = client.get(f"/projects/{other_project_id}")
        denied_create = client.post(
            "/projects",
            json={"name": "Member project", "workspace_id": owner_workspace_id},
            headers={"X-CSRF-Token": "member-csrf-token"},
        )
        denied_token = client.post(
            f"/api/v1/projects/{project.json()['id']}/ingestion-tokens",
            json={},
            headers={"X-CSRF-Token": "member-csrf-token"},
        )

        assert readable.status_code == 200
        assert hidden.status_code == 404
        assert denied_create.status_code == 403
        assert denied_token.status_code == 403
