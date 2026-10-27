import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.settings import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.payment import IdempotencyRecord, Payment, RequestLog
from app.schemas.payment import PaymentResponse
from app.services.payments import canonical_payment_payload, create_payment, hash_payment_payload

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> Iterator[TestClient]:
    database_name = make_url(settings.database_url).database
    if database_name is None or not database_name.endswith("_test"):
        pytest.fail("Integration API tests require a dedicated database ending in '_test'.")

    with TestClient(app) as test_client:
        yield test_client


def test_create_payment_persists_and_replays_idempotently(client: TestClient) -> None:
    key = str(uuid4())
    payload = {"amount_minor": 2599, "currency": "USD"}
    created = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["payment_id"].startswith("pay_")
    assert body["amount_minor"] == 2599
    assert body["currency"] == "USD"
    assert body["status"] == "pending"
    assert "id" not in body

    replayed = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert replayed.status_code == 200
    assert replayed.json() == body

    with SessionLocal() as session:
        assert session.scalar(select(Payment).where(Payment.public_id == body["payment_id"]))
        assert session.scalar(select(func.count()).select_from(Payment)) == 1

    with SessionLocal() as session:
        session.execute(
            update(Payment)
            .where(Payment.public_id == body["payment_id"])
            .values(status="succeeded")
        )
        session.commit()

    retried_after_change = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert retried_after_change.status_code == 200
    assert retried_after_change.json() == body
    with SessionLocal() as session:
        payment = session.scalar(select(Payment).where(Payment.public_id == body["payment_id"]))
        assert payment is not None
        assert payment.status == "succeeded"


def test_idempotency_key_conflict_is_documented_and_logged(client: TestClient) -> None:
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    assert client.post(
        "/api/v1/payments",
        json={"amount_minor": 100, "currency": "EUR"},
        headers=headers,
    ).status_code == 201

    conflict = client.post(
        "/api/v1/payments",
        json={"amount_minor": 101, "currency": "EUR"},
        headers=headers,
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reused"
    assert conflict.headers["X-Request-ID"] == conflict.json()["request_id"]

    with SessionLocal() as session:
        entries = session.scalars(select(RequestLog).order_by(RequestLog.request_at)).all()
        assert [entry.idempotency_outcome for entry in entries] == [
            "created",
            "payload_mismatch",
        ]
        assert entries[1].sanitized_error_code == "idempotency_key_reused"
        assert entries[1].outcome == "payload_conflict"
        assert entries[1].payment_id == entries[0].payment_id


@pytest.mark.parametrize(
    ("first_payload", "retry_payload"),
    [
        ({"amount_minor": 100, "currency": "USD"}, {"amount_minor": 101, "currency": "USD"}),
        ({"amount_minor": 100, "currency": "USD"}, {"amount_minor": 100, "currency": "EUR"}),
    ],
)
def test_changed_semantic_fields_conflict(
    client: TestClient,
    first_payload: dict[str, object],
    retry_payload: dict[str, object],
) -> None:
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    assert client.post("/api/v1/payments", json=first_payload, headers=headers).status_code == 201
    assert client.post("/api/v1/payments", json=retry_payload, headers=headers).status_code == 409
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1


def test_canonical_json_key_order_replays_same_result(client: TestClient) -> None:
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    first = client.post(
        "/api/v1/payments",
        content='{"amount_minor":345,"currency":"GBP"}',
        headers={**headers, "Content-Type": "application/json"},
    )
    retry = client.post(
        "/api/v1/payments",
        content='{"currency":"GBP","amount_minor":345}',
        headers={**headers, "Content-Type": "application/json"},
    )

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert canonical_payment_payload(345, "GBP") == '{"amount_minor":345,"currency":"GBP"}'
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1


def test_key_isolated_by_scope_and_distinct_keys_create_distinct_payments(
    client: TestClient,
) -> None:
    payload = {"amount_minor": 500, "currency": "USD"}
    first = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": "shared-key", "Idempotency-Scope": "workspace-a"},
    )
    other_scope = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": "shared-key", "Idempotency-Scope": "workspace-b"},
    )
    other_key = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": "another-key", "Idempotency-Scope": "workspace-a"},
    )
    replay = client.post(
        "/api/v1/payments",
        json=payload,
        headers={"Idempotency-Key": "shared-key", "Idempotency-Scope": "workspace-a"},
    )

    assert [
        first.status_code,
        other_scope.status_code,
        other_key.status_code,
        replay.status_code,
    ] == [201, 201, 201, 200]
    assert first.json()["payment_id"] == replay.json()["payment_id"]
    assert len(
        {
            first.json()["payment_id"],
            other_scope.json()["payment_id"],
            other_key.json()["payment_id"],
        }
    ) == 3
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 3


@pytest.mark.parametrize(
    ("payload", "headers"),
    [
        ({"amount_minor": 0, "currency": "USD"}, {"Idempotency-Key": "key"}),
        ({"amount_minor": 100.5, "currency": "USD"}, {"Idempotency-Key": "key"}),
        ({"amount_minor": "100", "currency": "USD"}, {"Idempotency-Key": "key"}),
        ({"amount_minor": True, "currency": "USD"}, {"Idempotency-Key": "key"}),
        (
            {"amount_minor": 100_000_001, "currency": "USD"},
            {"Idempotency-Key": "key"},
        ),
        ({"amount_minor": 100, "currency": "CAD"}, {"Idempotency-Key": "key"}),
        (
            {"amount_minor": 100, "currency": "USD", "card_number": "not-accepted"},
            {"Idempotency-Key": "key"},
        ),
        ({"amount_minor": 100, "currency": "USD"}, {}),
    ],
)
def test_invalid_payment_requests_return_consistent_422(
    client: TestClient, payload: dict[str, object], headers: dict[str, str]
) -> None:
    response = client.post("/api/v1/payments", json=payload, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "card_number" not in response.text
    assert "not-accepted" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    log_response = client.get("/api/v1/requests")
    assert log_response.json()["total"] == 1
    assert log_response.json()["items"][0]["http_status_code"] == 422
    assert log_response.json()["items"][0]["sanitized_error_code"] == "validation_error"
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


@pytest.mark.parametrize(
    "key",
    [
        "",
        "contains spaces",
        "bad/key",
        "x" * 256,
        "-must-start-with-alphanumeric",
    ],
)
def test_invalid_idempotency_key_is_rejected(client: TestClient, key: str) -> None:
    response = client.post(
        "/api/v1/payments",
        json={"amount_minor": 10, "currency": "USD"},
        headers={"Idempotency-Key": key},
    )

    assert response.status_code == 422
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_oversized_request_body_is_rejected_and_logged(client: TestClient) -> None:
    from app.core.settings import settings

    response = client.post(
        "/api/v1/payments",
        content=b"x" * (settings.max_request_body_bytes + 1),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid4()),
        },
    )

    assert response.status_code == 413, response.text
    assert response.json()["error"] == {
        "code": "request_too_large",
        "message": "The request body exceeds the configured size limit.",
    }
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
        log = session.scalar(
            select(RequestLog).where(
                RequestLog.request_id == response.json()["request_id"]
            )
        )
        assert log is not None
        assert log.http_status_code == 413
        assert log.outcome == "validation_error"
        assert log.sanitized_error_code == "request_too_large"


def test_chunked_oversized_request_body_is_rejected(client: TestClient) -> None:
    from app.core.settings import settings

    chunks = iter(
        [
            b"x" * settings.max_request_body_bytes,
            b"y",
        ]
    )
    response = client.post(
        "/api/v1/payments",
        content=chunks,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid4()),
        },
    )

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "request_too_large"
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0


def test_malformed_json_is_sanitized_and_does_not_create_records(client: TestClient) -> None:
    response = client.post(
        "/api/v1/payments",
        content=b'{"amount_minor": 10, "currency": "USD", "private_marker": "do-not-echo"',
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid4()),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "The request did not satisfy the API contract.",
    }
    assert "private_marker" not in response.text
    assert "do-not-echo" not in response.text
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_invalid_scope_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/payments",
        json={"amount_minor": 10, "currency": "USD"},
        headers={"Idempotency-Key": "valid-key", "Idempotency-Scope": "invalid scope"},
    )
    assert response.status_code == 422
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0


def test_concurrent_same_key_requests_create_one_payment(client: TestClient) -> None:
    barrier = Barrier(2)
    key = str(uuid4())

    def send_request() -> object:
        barrier.wait(timeout=10)
        return client.post(
            "/api/v1/payments",
            json={"amount_minor": 810, "currency": "EUR"},
            headers={"Idempotency-Key": key},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send_request(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert session.scalar(select(func.count()).select_from(RequestLog)) == 2


def test_concurrent_different_keys_create_two_payments(client: TestClient) -> None:
    barrier = Barrier(2)
    payload = {"amount_minor": 811, "currency": "EUR"}

    def send_request(key: str) -> object:
        barrier.wait(timeout=10)
        return client.post(
            "/api/v1/payments",
            json=payload,
            headers={"Idempotency-Key": key},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send_request, (str(uuid4()), str(uuid4()))))

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["payment_id"] != responses[1].json()["payment_id"]
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 2
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 2


def test_transaction_failure_rolls_back_payment_and_idempotency_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_response_validation(*args: object, **kwargs: object) -> PaymentResponse:
        raise RuntimeError("injected failure after payment flush")

    monkeypatch.setattr(PaymentResponse, "model_validate", fail_response_validation)
    with SessionLocal() as session:
        with pytest.raises(RuntimeError, match="injected failure"):
            create_payment(
                session,
                amount_minor=900,
                currency="USD",
                idempotency_key=str(uuid4()),
            )

    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_retry_survives_server_process_restart(client: TestClient) -> None:
    key = str(uuid4())
    payload = {"amount_minor": 912, "currency": "GBP"}
    del client

    def run_server_request() -> tuple[int, dict[str, object]]:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]

        environment = os.environ.copy()
        backend_path = str(Path(__file__).resolve().parents[1])
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, [backend_path, environment.get("PYTHONPATH")])
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "error",
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    pytest.fail(f"Uvicorn exited during startup with code {process.returncode}.")
                try:
                    with urlopen(f"{base_url}/health/ready", timeout=5):
                        break
                except (URLError, TimeoutError, OSError):
                    if time.monotonic() >= deadline:
                        pytest.fail("Uvicorn did not become ready.")
                    time.sleep(0.1)

            request = Request(
                f"{base_url}/api/v1/payments",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": key,
                },
                method="POST",
            )
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        finally:
            process.terminate()
            process.wait(timeout=10)

    first_status, first_body = run_server_request()
    replay_status, replay_body = run_server_request()
    assert first_status == 201
    assert replay_status == 200
    assert replay_body == first_body
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1


def test_database_unique_constraint_is_final_safeguard(client: TestClient) -> None:
    del client
    record = IdempotencyRecord(
        scope="constraint-scope",
        idempotency_key="constraint-key",
        request_hash=hash_payment_payload(100, "USD"),
    )
    with SessionLocal() as session:
        session.add(record)
        session.commit()
        session.add(
            IdempotencyRecord(
                scope="constraint-scope",
                idempotency_key="constraint-key",
                request_hash=hash_payment_payload(101, "USD"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_conflict_replay_keeps_sqlalchemy_session_usable() -> None:
    with SessionLocal() as session:
        first = create_payment(
            session,
            amount_minor=101,
            currency="USD",
            idempotency_key="same-session-key",
            scope="same-session-scope",
        )
        replay = create_payment(
            session,
            amount_minor=101,
            currency="USD",
            idempotency_key="same-session-key",
            scope="same-session-scope",
        )
        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.response == first.response
        assert session.scalar(select(func.count()).select_from(Payment)) == 1


def test_payment_retrieval_and_pagination(client: TestClient) -> None:
    payment_ids = []
    for amount in (120, 240, 360):
        response = client.post(
            "/api/v1/payments",
            json={"amount_minor": amount, "currency": "GBP"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201
        payment_ids.append(response.json()["payment_id"])

    detail = client.get(f"/api/v1/payments/{payment_ids[0]}")
    assert detail.status_code == 200
    assert detail.json()["payment_id"] == payment_ids[0]

    first_page = client.get("/api/v1/payments", params={"limit": 2, "offset": 0})
    second_page = client.get("/api/v1/payments", params={"limit": 2, "offset": 2})
    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert first_page.json()["limit"] == 2
    assert first_page.json()["offset"] == 0
    assert len(first_page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    with SessionLocal() as session:
        expected_order = session.scalars(
            select(Payment.public_id).order_by(Payment.created_at.desc(), Payment.id.desc())
        ).all()
    assert [
        item["payment_id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    ] == expected_order

    assert client.get("/api/v1/payments", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/payments", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/payments", params={"offset": -1}).status_code == 422
    assert client.get("/api/v1/payments", params={"offset": 1_000_001}).status_code == 422
    assert client.get("/api/v1/payments/not-a-payment").status_code == 404


def test_unexpected_exception_is_sanitized_for_api_clients(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_unexpected(*args: object, **kwargs: object) -> object:
        raise RuntimeError("private connection string and stack detail")

    monkeypatch.setattr("app.api.routes.create_payment", raise_unexpected)
    with TestClient(app, raise_server_exceptions=False) as sanitized_client:
        response = sanitized_client.post(
            "/api/v1/payments",
            json={"amount_minor": 400, "currency": "USD"},
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "The request could not be completed.",
    }
    assert "private connection string" not in response.text
    assert "RuntimeError" not in response.text
    assert response.headers["X-Request-ID"] == response.json()["request_id"]
    with SessionLocal() as session:
        log = session.scalar(
            select(RequestLog).where(
                RequestLog.request_id == response.json()["request_id"]
            )
        )
        assert log is not None
        assert log.outcome == "handled_error"
        assert log.sanitized_error_code == "internal_error"


def test_request_lookup_metrics_and_health_contracts(client: TestClient) -> None:
    created = client.post(
        "/api/v1/payments",
        json={"amount_minor": 700, "currency": "USD"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    request_id = created.headers["X-Request-ID"]

    requests = client.get("/api/v1/requests", params={"limit": 1})
    assert requests.status_code == 200
    assert requests.json()["total"] == 1
    log_entry = requests.json()["items"][0]
    assert log_entry["request_id"] == request_id
    assert log_entry["payment_id"] == created.json()["payment_id"]
    assert log_entry["api_path"] == "/api/v1/payments"
    assert log_entry["outcome"] == "payment_created"
    assert log_entry["idempotency_outcome"] == "created"
    assert "Idempotency-Key" not in str(log_entry)

    detail = client.get(f"/api/v1/requests/{request_id}")
    assert detail.status_code == 200
    assert detail.json() == log_entry
    missing_request = client.get(f"/api/v1/requests/{uuid4()}")
    assert missing_request.status_code == 404

    metrics = client.get("/api/v1/metrics/summary")
    assert metrics.status_code == 200
    assert metrics.json() == {
        "period_start": None,
        "period_end": None,
        "total_payments": 1,
        "payments_by_status": {"pending": 1, "succeeded": 0, "failed": 0},
        "total_requests": 4,
        "payment_attempts": 1,
        "successful_requests": 3,
        "conflicts": 0,
        "idempotency_replays": 0,
    }
    with SessionLocal() as session:
        missing_row = session.scalar(
            select(RequestLog).where(
                RequestLog.request_id == missing_request.headers["X-Request-ID"]
            )
        )
        assert missing_row is not None
        assert missing_row.outcome == "handled_error"
        assert missing_row.sanitized_error_code == "request_not_found"
    assert client.get("/health").json() == {"status": "alive"}


def test_empty_metrics_return_zeroes_and_empty_status_counts(client: TestClient) -> None:
    response = client.get("/api/v1/metrics/summary")

    assert response.status_code == 200
    assert response.json() == {
        "period_start": None,
        "period_end": None,
        "total_payments": 0,
        "payments_by_status": {"pending": 0, "succeeded": 0, "failed": 0},
        "total_requests": 0,
        "payment_attempts": 0,
        "successful_requests": 0,
        "conflicts": 0,
        "idempotency_replays": 0,
    }


def test_request_ids_and_normalized_paths_do_not_contain_path_parameters(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/payments",
        json={"amount_minor": 10, "currency": "USD"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    response_id = client.get(f"/api/v1/payments/{created.json()['payment_id']}")
    assert created.headers["X-Request-ID"] != response_id.headers["X-Request-ID"]

    with SessionLocal() as session:
        rows = session.scalars(select(RequestLog).order_by(RequestLog.request_at)).all()
    assert len(rows) == 2
    assert rows[0].api_path == "/api/v1/payments"
    assert rows[1].api_path == "/api/v1/payments/{payment_id}"
    assert rows[1].outcome == "success"
    assert rows[1].payment_id == rows[0].payment_id


def test_optional_request_logging_failure_does_not_change_payment_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_logging_session():
        raise RuntimeError("logging database unavailable")

    monkeypatch.setattr("app.main.SessionLocal", fail_logging_session)
    response = client.post(
        "/api/v1/payments",
        json={"amount_minor": 777, "currency": "USD"},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 201
    assert response.json()["payment_id"].startswith("pay_")
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1


def test_metrics_count_replays_and_conflicts_from_request_logs(client: TestClient) -> None:
    key = str(uuid4())
    headers = {"Idempotency-Key": key}
    payload = {"amount_minor": 1500, "currency": "USD"}
    created = client.post("/api/v1/payments", json=payload, headers=headers)
    replayed = client.post("/api/v1/payments", json=payload, headers=headers)
    conflict = client.post(
        "/api/v1/payments",
        json={"amount_minor": 1501, "currency": "USD"},
        headers=headers,
    )
    succeeded = client.post(
        "/api/v1/payments",
        json={"amount_minor": 2500, "currency": "EUR"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert [
        created.status_code,
        replayed.status_code,
        conflict.status_code,
        succeeded.status_code,
    ] == [201, 200, 409, 201]

    with SessionLocal() as session:
        payment = session.scalar(
            select(Payment).where(Payment.public_id == succeeded.json()["payment_id"])
        )
        assert payment is not None
        session.execute(
            update(Payment).where(Payment.id == payment.id).values(status="succeeded")
        )
        session.commit()

    metrics = client.get("/api/v1/metrics/summary").json()
    assert metrics["total_payments"] == 2
    assert metrics["payments_by_status"] == {"pending": 1, "succeeded": 1, "failed": 0}
    assert metrics["payment_attempts"] == 4
    assert metrics["total_requests"] == 4
    assert metrics["successful_requests"] == 3
    assert metrics["conflicts"] == 1
    assert metrics["idempotency_replays"] == 1

    with SessionLocal() as session:
        request_ids = [
            created.headers["X-Request-ID"],
            replayed.headers["X-Request-ID"],
            conflict.headers["X-Request-ID"],
            succeeded.headers["X-Request-ID"],
        ]
        logged = session.scalars(
            select(RequestLog).where(RequestLog.request_id.in_(request_ids))
        ).all()
    outcomes = {str(row.request_id): row.outcome for row in logged}
    assert outcomes == {
        created.headers["X-Request-ID"]: "payment_created",
        replayed.headers["X-Request-ID"]: "idempotency_replay",
        conflict.headers["X-Request-ID"]: "payload_conflict",
        succeeded.headers["X-Request-ID"]: "payment_created",
    }


def test_metrics_period_is_utc_half_open_and_applies_to_both_tables(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/v1/payments",
        json={"amount_minor": 201, "currency": "USD"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    upper = client.post(
        "/api/v1/payments",
        json={"amount_minor": 202, "currency": "EUR"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    before = client.post(
        "/api/v1/payments",
        json={"amount_minor": 203, "currency": "GBP"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert first.status_code == upper.status_code == before.status_code == 201

    start = "2030-05-10T12:00:00Z"
    end = "2030-05-11T12:00:00Z"
    with SessionLocal() as session:
        first_payment = session.scalar(
            select(Payment).where(Payment.public_id == first.json()["payment_id"])
        )
        upper_payment = session.scalar(
            select(Payment).where(Payment.public_id == upper.json()["payment_id"])
        )
        before_payment = session.scalar(
            select(Payment).where(Payment.public_id == before.json()["payment_id"])
        )
        assert first_payment and upper_payment and before_payment
        session.execute(
            update(Payment)
            .where(Payment.id == first_payment.id)
            .values(created_at=start)
        )
        session.execute(
            update(Payment)
            .where(Payment.id == upper_payment.id)
            .values(created_at=end)
        )
        session.execute(
            update(Payment)
            .where(Payment.id == before_payment.id)
            .values(created_at="2030-05-10T11:59:59Z")
        )
        for response, timestamp in (
            (first, start),
            (upper, end),
            (before, "2030-05-10T11:59:59Z"),
        ):
            session.execute(
                update(RequestLog)
                .where(RequestLog.request_id == response.headers["X-Request-ID"])
                .values(request_at=timestamp)
            )
        session.commit()

    response = client.get(
        "/api/v1/metrics/summary",
        params={"start": start, "end": end},
    )
    assert response.status_code == 200
    assert response.json()["period_start"] == "2030-05-10T12:00:00Z"
    assert response.json()["period_end"] == "2030-05-11T12:00:00Z"
    assert response.json()["total_payments"] == 1
    assert response.json()["total_requests"] == 1
    assert response.json()["successful_requests"] == 1
    assert response.json()["payment_attempts"] == 1


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2030-05-11T12:00:00Z", "2030-05-10T12:00:00Z"),
        ("2030-05-10T12:00:00", "2030-05-11T12:00:00Z"),
    ],
)
def test_metrics_reject_invalid_periods(client: TestClient, start: str, end: str) -> None:
    response = client.get("/api/v1/metrics/summary", params={"start": start, "end": end})
    assert response.status_code == 422


def test_openapi_documents_payment_statuses_and_error_shape(client: TestClient) -> None:
    del client
    schema = app.openapi()

    assert {"200", "201", "409", "422", "500", "503"} <= set(
        schema["paths"]["/api/v1/payments"]["post"]["responses"]
    )
    assert (
        schema["paths"]["/api/v1/payments"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/CreatePaymentRequest"
    )
