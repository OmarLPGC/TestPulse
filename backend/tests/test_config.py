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


def test_junit_ingestion_limits_default_and_can_be_reduced() -> None:
    settings = Settings.from_environment(
        {
            "POSTGRES_DB": "testpulse",
            "POSTGRES_USER": "testpulse",
            "POSTGRES_PASSWORD": "local-only",
            "MAX_JUNIT_REPORT_BYTES": "4096",
            "MAX_JUNIT_TEST_CASES": "250",
        }
    )

    assert settings.max_junit_report_bytes == 4096
    assert settings.max_junit_test_cases == 250


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("MAX_JUNIT_REPORT_BYTES", "0"),
        ("MAX_JUNIT_REPORT_BYTES", str(10 * 1024 * 1024 + 1)),
        ("MAX_JUNIT_TEST_CASES", "not-an-integer"),
    ],
)
def test_junit_ingestion_limits_reject_invalid_values(setting: str, value: str) -> None:
    values = {
        "POSTGRES_DB": "testpulse",
        "POSTGRES_USER": "testpulse",
        "POSTGRES_PASSWORD": "local-only",
        setting: value,
    }

    with pytest.raises(ConfigurationError):
        Settings.from_environment(values)
