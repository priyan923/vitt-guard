import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.settings import Settings, settings
from app.main import app


def test_production_settings_require_long_auth_password_and_explicit_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:pass@localhost/db",
            app_env="production",
            auth_enabled=True,
            auth_username="operator",
            auth_password="short",
            cors_allowed_origins="https://dashboard.example.test",
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:pass@localhost/db",
            app_env="production",
            auth_enabled=True,
            auth_username="operator",
            auth_password="a" * 32,
        )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:pass@localhost/db",
            app_env="production",
            auth_enabled=True,
            auth_username="operator",
            auth_password="a" * 32,
            cors_allowed_origins="http://dashboard.example.test",
        )


def test_production_settings_accept_configured_auth_and_origin() -> None:
    configured = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost/db",
        app_env="production",
        auth_enabled=True,
        auth_username="operator",
        auth_password="a" * 32,
        cors_allowed_origins="https://dashboard.example.test",
    )

    assert configured.app_env == "production"
    assert configured.allowed_origins == ["https://dashboard.example.test"]


def test_protected_auth_verification_requires_valid_basic_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_username", "demo-operator")
    monkeypatch.setattr(settings, "auth_password", "correct-horse-battery")

    with TestClient(app) as client:
        missing = client.get("/auth/verify")
        incorrect = client.get(
            "/auth/verify",
            auth=("demo-operator", "incorrect"),
        )
        valid = client.get(
            "/auth/verify",
            auth=("demo-operator", "correct-horse-battery"),
        )
        status = client.get("/auth/status")

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Basic"
    assert missing.json()["error"]["code"] == "authentication_required"
    assert "correct-horse-battery" not in missing.text
    assert incorrect.status_code == 401
    assert valid.status_code == 200
    assert valid.json() == {"status": "authenticated"}
    assert status.json() == {"authentication_required": True}


def test_payment_api_requires_authentication_without_database_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_username", "demo-operator")
    monkeypatch.setattr(settings, "auth_password", "correct-horse-battery")

    def fail_if_database_logging_is_attempted() -> None:
        raise AssertionError("unauthenticated requests must not write database logs")

    monkeypatch.setattr(
        "app.main.SessionLocal",
        fail_if_database_logging_is_attempted,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/metrics/summary")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
