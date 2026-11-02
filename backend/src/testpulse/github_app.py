from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote

import httpx

GITHUB_API_URL = "https://api.github.com"
GITHUB_OAUTH_URL = "https://github.com/login/oauth"
GITHUB_API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    def __init__(
        self,
        status_code: Optional[int] = None,
        *,
        provider_error: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.provider_error = provider_error
        super().__init__("GitHub request failed.")


@dataclass(frozen=True)
class GitHubCredentials:
    access_token: str
    refresh_token: Optional[str]
    expires_in: Optional[int]


class GitHubAppClient:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 10.0) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

    def authorization_url(self, callback_url: str, state: str) -> str:
        return str(
            httpx.URL("https://github.com/login/oauth/authorize").copy_merge_params(
                {"client_id": self.client_id, "redirect_uri": callback_url, "state": state}
            )
        )

    def exchange_code(self, code: str) -> GitHubCredentials:
        return self._get_credentials(
            self._oauth_post({"code": code, "grant_type": "authorization_code"})
        )

    def refresh_credentials(self, refresh_token: str) -> GitHubCredentials:
        return self._get_credentials(
            self._oauth_post({"refresh_token": refresh_token, "grant_type": "refresh_token"})
        )

    def get_authenticated_user(self, access_token: str) -> dict[str, Any]:
        data = self._api_get("/user", access_token)
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            raise GitHubError
        if not isinstance(data.get("login"), str) or not data["login"]:
            raise GitHubError
        return data

    def list_repositories(
        self, access_token: str, *, page: int, per_page: int
    ) -> tuple[list[dict[str, Any]], bool]:
        response = self._api_response(
            "/user/repos",
            access_token,
            params={
                "affiliation": "owner,collaborator,organization_member",
                "sort": "full_name",
                "direction": "asc",
                "visibility": "all",
                "page": page,
                "per_page": per_page,
            },
        )
        data = self._json(response)
        if not isinstance(data, list):
            raise GitHubError(response.status_code)
        repositories = [self._repository(item) for item in data]
        has_next = 'rel="next"' in response.headers.get("Link", "")
        return repositories, has_next

    def get_repository(self, access_token: str, full_name: str) -> dict[str, Any]:
        path = "/repos/" + quote(full_name, safe="/")
        return self._repository(self._api_get(path, access_token))

    def _oauth_post(self, payload: dict[str, str]) -> dict[str, Any]:
        try:
            response = httpx.post(
                GITHUB_OAUTH_URL + "/access_token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    **payload,
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise GitHubError from exc
        data = self._json(response)
        if response.is_error or not isinstance(data, dict) or data.get("error"):
            provider_error = data.get("error") if isinstance(data, dict) else None
            if (
                not isinstance(provider_error, str)
                or not provider_error.isascii()
                or not provider_error.replace("_", "").replace("-", "").isalnum()
            ):
                provider_error = None
            raise GitHubError(
                response.status_code,
                provider_error=provider_error,
            )
        return data

    def _api_get(self, path: str, access_token: str) -> Any:
        response = self._api_response(path, access_token)
        return self._json(response)

    def _api_response(
        self, path: str, access_token: str, *, params: Optional[dict[str, Any]] = None
    ) -> httpx.Response:
        try:
            response = httpx.get(
                GITHUB_API_URL + path,
                params=params,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                },
                timeout=self.timeout,
            )
        except httpx.RequestError as exc:
            raise GitHubError from exc
        if response.is_error:
            raise GitHubError(response.status_code)
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubError(response.status_code) from exc

    @staticmethod
    def _get_credentials(data: dict[str, Any]) -> GitHubCredentials:
        access_token = data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubError
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise GitHubError
        if expires_in is not None and (not isinstance(expires_in, int) or expires_in <= 0):
            raise GitHubError
        return GitHubCredentials(access_token, refresh_token, expires_in)

    @staticmethod
    def _repository(data: Any) -> dict[str, Any]:
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("id"), int)
            or not isinstance(data.get("full_name"), str)
            or not isinstance(data.get("html_url"), str)
        ):
            raise GitHubError
        permissions = data.get("permissions")
        return {
            "id": data["id"],
            "full_name": data["full_name"],
            "html_url": data["html_url"],
            "private": bool(data.get("private", False)),
            "permissions": permissions if isinstance(permissions, dict) else {},
        }
