import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.engine import URL


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: URL

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

        database_url = URL.create(
            "postgresql+psycopg",
            username=values["POSTGRES_USER"],
            password=values["POSTGRES_PASSWORD"],
            host=values.get("POSTGRES_HOST", "127.0.0.1"),
            port=port,
            database=values["POSTGRES_DB"],
        )
        return cls(
            app_env=values.get("APP_ENV", "development"),
            database_url=database_url,
        )


def load_settings() -> Settings:
    load_dotenv()
    return Settings.from_environment()
