import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import URL

MAX_JUNIT_REPORT_BYTES = 10 * 1024 * 1024
MAX_JUNIT_TEST_CASES = 100_000
DEFAULT_SESSION_TTL_SECONDS = 14 * 24 * 60 * 60


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: URL
    max_junit_report_bytes: int = MAX_JUNIT_REPORT_BYTES
    max_junit_test_cases: int = MAX_JUNIT_TEST_CASES
    github_app_client_id: Optional[str] = None
    github_app_client_secret: Optional[str] = None
    github_app_callback_url: Optional[str] = None
    public_base_url: Optional[str] = None
    github_token_encryption_key: Optional[str] = None
    bootstrap_github_user_id: Optional[int] = None
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS

    def __post_init__(self) -> None:
        if not 1 <= self.max_junit_report_bytes <= MAX_JUNIT_REPORT_BYTES:
            raise ConfigurationError(
                f"max_junit_report_bytes must be between 1 and {MAX_JUNIT_REPORT_BYTES}."
            )
        if not 1 <= self.max_junit_test_cases <= MAX_JUNIT_TEST_CASES:
            raise ConfigurationError(
                f"max_junit_test_cases must be between 1 and {MAX_JUNIT_TEST_CASES}."
            )
        if not 300 <= self.session_ttl_seconds <= 90 * 24 * 60 * 60:
            raise ConfigurationError("session_ttl_seconds must be between 300 and 7776000.")
        github_values = (
            self.github_app_client_id,
            self.github_app_client_secret,
            self.github_app_callback_url,
            self.public_base_url,
            self.github_token_encryption_key,
        )
        if any(github_values) and not all(github_values):
            raise ConfigurationError(
                "GitHub App client ID, secret, callback URL, public base URL, and "
                "token encryption key must be configured together."
            )
        if self.app_env == "production" and not all(github_values):
            raise ConfigurationError("GitHub App settings are required in production.")
        if self.github_token_encryption_key:
            try:
                encoded_key = self.github_token_encryption_key.encode("ascii")
                key = base64.b64decode(
                    encoded_key + b"=" * (-len(encoded_key) % 4),
                    altchars=b"-_",
                    validate=True,
                )
            except (UnicodeEncodeError, ValueError) as exc:
                raise ConfigurationError(
                    "GITHUB_TOKEN_ENCRYPTION_KEY must be URL-safe base64 for 32 random bytes."
                ) from exc
            if len(key) != 32:
                raise ConfigurationError(
                    "GITHUB_TOKEN_ENCRYPTION_KEY must encode exactly 32 random bytes."
                )
        if self.public_base_url:
            public = urlsplit(self.public_base_url)
            if (
                public.scheme not in {"http", "https"}
                or not public.netloc
                or public.path not in {"", "/"}
                or public.query
                or public.fragment
                or public.username
                or public.password
            ):
                raise ConfigurationError("PUBLIC_BASE_URL must be an origin without a path.")
            if self.app_env == "production" and public.scheme != "https":
                raise ConfigurationError("PUBLIC_BASE_URL must use HTTPS in production.")
        if self.github_app_callback_url and self.public_base_url:
            callback = urlsplit(self.github_app_callback_url)
            public = urlsplit(self.public_base_url)
            if (
                callback.scheme != public.scheme
                or callback.netloc != public.netloc
                or not callback.path
                or callback.query
                or callback.fragment
                or callback.username
                or callback.password
            ):
                raise ConfigurationError(
                    "GITHUB_APP_CALLBACK_URL must use the public origin and a callback path."
                )
            if callback.path != "/api/v1/auth/github/callback":
                raise ConfigurationError(
                    "GITHUB_APP_CALLBACK_URL path must be /api/v1/auth/github/callback."
                )
        if self.bootstrap_github_user_id is not None and self.bootstrap_github_user_id < 1:
            raise ConfigurationError("TESTPULSE_BOOTSTRAP_GITHUB_USER_ID must be positive.")

    @classmethod
    def from_environment(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        values = os.environ if environ is None else environ
        required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
        missing = [name for name in required if not values.get(name)]
        if missing:
            names = ", ".join(missing)
            raise ConfigurationError(
                f"Missing required environment variable(s): {names}. "
                "Copy .env.example to .env and set the values."
            )

        try:
            port = int(values.get("POSTGRES_PORT", "5432"))
        except ValueError as exc:
            raise ConfigurationError("POSTGRES_PORT must be an integer.") from exc
        if not 1 <= port <= 65535:
            raise ConfigurationError("POSTGRES_PORT must be between 1 and 65535.")

        try:
            max_report_bytes = int(
                values.get("MAX_JUNIT_REPORT_BYTES", str(MAX_JUNIT_REPORT_BYTES))
            )
            max_test_cases = int(values.get("MAX_JUNIT_TEST_CASES", str(MAX_JUNIT_TEST_CASES)))
            session_ttl_seconds = int(
                values.get("SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))
            )
        except ValueError as exc:
            raise ConfigurationError(
                "MAX_JUNIT_REPORT_BYTES, MAX_JUNIT_TEST_CASES, and SESSION_TTL_SECONDS "
                "must be integers."
            ) from exc
        if not 1 <= max_report_bytes <= MAX_JUNIT_REPORT_BYTES:
            raise ConfigurationError(
                f"MAX_JUNIT_REPORT_BYTES must be between 1 and {MAX_JUNIT_REPORT_BYTES}."
            )
        if not 1 <= max_test_cases <= MAX_JUNIT_TEST_CASES:
            raise ConfigurationError(
                f"MAX_JUNIT_TEST_CASES must be between 1 and {MAX_JUNIT_TEST_CASES}."
            )
        bootstrap_user_id = values.get("TESTPULSE_BOOTSTRAP_GITHUB_USER_ID")
        try:
            parsed_bootstrap_user_id = int(bootstrap_user_id) if bootstrap_user_id else None
        except ValueError as exc:
            raise ConfigurationError(
                "TESTPULSE_BOOTSTRAP_GITHUB_USER_ID must be a positive integer."
            ) from exc

        database_url = URL.create(
            "postgresql+psycopg",
            username=values["POSTGRES_USER"],
            password=values["POSTGRES_PASSWORD"],
            host=values.get("POSTGRES_HOST", "127.0.0.1"),
            port=port,
            database=values["POSTGRES_DB"],
        )
        return cls(
            app_env=values.get("APP_ENV", "development").lower(),
            database_url=database_url,
            max_junit_report_bytes=max_report_bytes,
            max_junit_test_cases=max_test_cases,
            github_app_client_id=values.get("GITHUB_APP_CLIENT_ID") or None,
            github_app_client_secret=values.get("GITHUB_APP_CLIENT_SECRET") or None,
            github_app_callback_url=values.get("GITHUB_APP_CALLBACK_URL") or None,
            public_base_url=values.get("PUBLIC_BASE_URL") or None,
            github_token_encryption_key=values.get("GITHUB_TOKEN_ENCRYPTION_KEY") or None,
            bootstrap_github_user_id=parsed_bootstrap_user_id,
            session_ttl_seconds=session_ttl_seconds,
        )


def load_settings() -> Settings:
    load_dotenv()
    return Settings.from_environment()
