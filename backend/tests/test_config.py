import pytest
from sqlalchemy.engine import URL
from testpulse.config import ConfigurationError, Settings


@pytest.mark.parametrize("missing", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"])
def test_required_database_settings_fail_clearly(missing: str) -> None:
    values = {
        "POSTGRES_DB": "testpulse",
        "POSTGRES_USER": "testpulse",
        "POSTGRES_PASSWORD": "local-only",
    }
    del values[missing]

    with pytest.raises(ConfigurationError, match=missing):
        Settings.from_environment(values)


def test_database_url_escapes_credentials() -> None:
    settings = Settings.from_environment(
        {
            "POSTGRES_DB": "testpulse",
            "POSTGRES_USER": "testpulse",
            "POSTGRES_PASSWORD": "p@ss/word",
        }
    )

    assert settings.database_url == URL.create(
        "postgresql+psycopg",
        username="testpulse",
        password="p@ss/word",
        host="127.0.0.1",
        port=5432,
        database="testpulse",
    )
