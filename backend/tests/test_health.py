import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.exc import OperationalError

from app.main import app


def request_health(path: str) -> Response:
    async def send_request() -> Response:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get(path)

    return asyncio.run(send_request())


def test_liveness_does_not_require_database() -> None:
    response = request_health("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_liveness_does_not_attempt_optional_database_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_logging() -> None:
        raise AssertionError("liveness must not access the database")

    monkeypatch.setattr("app.main.SessionLocal", fail_logging)
    response = request_health("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_unavailable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_connection() -> None:
        raise OperationalError("SELECT 1", {}, OSError("database unavailable"))

    monkeypatch.setattr("app.main.engine.connect", fail_connection)

    response = request_health("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "database_unavailable",
        "message": "The database is temporarily unavailable.",
    }
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.integration
def test_readiness_uses_postgresql() -> None:
    response = request_health("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_cors_allows_only_configured_origin_and_exposes_request_id() -> None:
    async def send_requests() -> tuple[Response, Response, Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            allowed = await client.options(
                "/api/v1/payments",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": (
                        "authorization,content-type,idempotency-key,idempotency-scope"
                    ),
                },
            )
            denied = await client.get(
                "/health/live",
                headers={"Origin": "https://untrusted.example.test"},
            )
            exposed = await client.get(
                "/health/live",
                headers={"Origin": "http://localhost:5173"},
            )
            return allowed, denied, exposed

    allowed, denied, exposed = asyncio.run(send_requests())
    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "authorization" in allowed.headers["Access-Control-Allow-Headers"]
    assert "Access-Control-Allow-Credentials" not in allowed.headers
    assert "X-Request-ID" in exposed.headers["Access-Control-Expose-Headers"]
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_application_lifespan_disposes_database_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disposed = False

    def dispose() -> None:
        nonlocal disposed
        disposed = True

    monkeypatch.setattr("app.main.engine.dispose", dispose)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200

    assert disposed
