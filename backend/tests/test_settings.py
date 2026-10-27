import pytest
from pydantic import ValidationError

from app.core.settings import Settings


def test_database_url_must_be_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///local.db",
        "postgresql://user:password@localhost/vitt_guard",
        "postgresql+psycopg://localhost/vitt_guard",
    ],
)
def test_database_url_rejects_unsupported_or_incomplete_values(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_origins_require_explicit_http_origins() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost/db",
        cors_allowed_origins="https://dashboard.example.test, http://localhost:5173/",
    )

    assert settings.allowed_origins == [
        "https://dashboard.example.test",
        "http://localhost:5173",
    ]


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "https://example.test/path",
        "https://user:password@example.test",
        "ftp://example.test",
        "https://example.test?token=secret",
    ],
)
def test_cors_origins_reject_wildcards_and_non_origins(origins: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:pass@localhost/db",
            cors_allowed_origins=origins,
        )


@pytest.mark.parametrize("body_limit", [0, 999, 1_048_577])
def test_request_body_limit_has_safe_bounds(body_limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:pass@localhost/db",
            max_request_body_bytes=body_limit,
        )
