import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.auth import require_api_auth
from app.core.settings import settings
from app.db.session import SessionLocal, engine
from app.models.payment import RequestLog
from app.schemas.payment import ApiErrorResponse
from app.services.payments import PaymentRequestError

logger = logging.getLogger(__name__)


class RequestSizeLimitMiddleware:
    def __init__(
        self,
        app: Callable[..., Any],
        *,
        maximum_bytes: int,
    ) -> None:
        self.app = app
        self.maximum_bytes = maximum_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_value = headers.get(b"content-length")
        content_length: int | None = None
        if content_length_value is not None:
            try:
                content_length = int(content_length_value)
            except ValueError:
                content_length = None
        if content_length is not None and content_length > self.maximum_bytes:
            await self.reject_oversized_request(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.maximum_bytes:
                await self.reject_oversized_request(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        body_sent = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal body_sent
            if body_sent:
                return {"type": "http.disconnect"}
            body_sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_receive, send)

    async def reject_oversized_request(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        state = scope.setdefault("state", {})
        request_id = state.get("request_id")
        if not isinstance(request_id, UUID):
            request_id = uuid4()
            state["request_id"] = request_id
        state["sanitized_error_code"] = "request_too_large"
        state["outcome"] = "validation_error"
        response = JSONResponse(
            status_code=413,
            content=error_body(
                request_id,
                "request_too_large",
                "The request body exceeds the configured size limit.",
            ),
            headers={"X-Request-ID": str(request_id)},
        )
        await response(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await run_in_threadpool(engine.dispose)


app = FastAPI(
    title="Vitt Guard API",
    version="0.1.0",
    description="A simulated payment API. No real financial transactions are performed.",
    lifespan=lifespan,
)
app.include_router(router)
app.add_middleware(
    RequestSizeLimitMiddleware,
    maximum_bytes=settings.max_request_body_bytes,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "Idempotency-Scope",
    ],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


def error_body(request_id: UUID, code: str, message: str) -> dict[str, object]:
    return ApiErrorResponse(
        error={"code": code, "message": message},
        request_id=request_id,
    ).model_dump(mode="json")


@app.get("/auth/status", tags=["authentication"], include_in_schema=False)
def auth_status() -> dict[str, bool]:
    return {"authentication_required": settings.auth_enabled}


@app.get(
    "/auth/verify",
    tags=["authentication"],
    include_in_schema=False,
    dependencies=[Depends(require_api_auth)],
)
def verify_authentication() -> dict[str, Literal["authenticated"]]:
    return {"status": "authenticated"}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    del error
    request.state.sanitized_error_code = "validation_error"
    return JSONResponse(
        status_code=422,
        content=error_body(
            request.state.request_id,
            "validation_error",
            "The request did not satisfy the API contract.",
        ),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, error: HTTPException) -> JSONResponse:
    if isinstance(error.detail, dict):
        candidate_code = error.detail.get("code")
    else:
        candidate_code = None
    known_messages = {
        "authentication_required": "Valid credentials are required.",
        "payment_not_found": "Payment was not found.",
        "request_not_found": "Request was not found.",
        "invalid_metrics_period": "The end of the metrics period must be after its start.",
        "database_unavailable": "The database is temporarily unavailable.",
    }
    code = (
        candidate_code
        if isinstance(candidate_code, str) and candidate_code in known_messages
        else "http_error"
    )
    message = known_messages.get(code, "The request could not be completed.")
    request.state.sanitized_error_code = code
    request.state.outcome = (
        "database_error"
        if code in {"database_unavailable", "database_error", "request_logging_unavailable"}
        else "payload_conflict"
        if error.status_code == 409
        else "handled_error"
    )
    return JSONResponse(
        status_code=error.status_code,
        content=error_body(request.state.request_id, code, message),
        headers=error.headers,
    )


@app.exception_handler(PaymentRequestError)
async def payment_error_handler(request: Request, error: PaymentRequestError) -> JSONResponse:
    request.state.sanitized_error_code = error.code
    request.state.outcome = (
        "payload_conflict" if error.status_code == 409 else "handled_error"
    )
    return JSONResponse(
        status_code=error.status_code,
        content=error_body(request.state.request_id, error.code, error.message),
    )


@app.exception_handler(OperationalError)
async def database_error_handler(request: Request, error: OperationalError) -> JSONResponse:
    logger.error(
        "Database operation failed (request_id=%s, error_type=%s)",
        request.state.request_id,
        type(error).__name__,
    )
    request.state.sanitized_error_code = "database_unavailable"
    request.state.outcome = "database_error"
    return JSONResponse(
        status_code=503,
        content=error_body(
            request.state.request_id,
            "database_unavailable",
            "The database is temporarily unavailable; retry safely.",
        ),
    )


@app.exception_handler(SQLAlchemyError)
async def database_operation_error_handler(
    request: Request, error: SQLAlchemyError
) -> JSONResponse:
    logger.error(
        "Database operation failed (request_id=%s, error_type=%s)",
        request.state.request_id,
        type(error).__name__,
    )
    request.state.sanitized_error_code = "database_error"
    request.state.outcome = "database_error"
    return JSONResponse(
        status_code=500,
        content=error_body(
            request.state.request_id,
            "database_error",
            "The database operation could not be completed.",
        ),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.error(
        "Unhandled request failure (request_id=%s, error_type=%s)",
        request.state.request_id,
        type(error).__name__,
    )
    request.state.sanitized_error_code = "internal_error"
    request.state.outcome = "handled_error"
    return JSONResponse(
        status_code=500,
        content=error_body(
            request.state.request_id,
            "internal_error",
            "The request could not be completed.",
        ),
    )


@app.middleware("http")
async def trace_api_requests(request: Request, call_next):
    request_id = uuid4()
    request.state.request_id = request_id
    started_at = time.monotonic_ns()
    try:
        response = await call_next(request)
    except Exception as error:
        response = await unexpected_error_handler(request, error)
    response.headers["X-Request-ID"] = str(request_id)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"

    request_path = request.url.path
    is_observed_api_request = (
        request_path.startswith("/api/v1/") and request.method.upper() != "OPTIONS"
    ) or request_path == "/health/ready"
    if settings.auth_enabled and response.status_code == 401:
        route = request.scope.get("route")
        normalized_path = getattr(route, "path", "/unmatched")
        logger.warning(
            "Authentication rejected (request_id=%s, method=%s, api_path=%s)",
            request_id,
            request.method.upper(),
            normalized_path if isinstance(normalized_path, str) else "/unmatched",
        )
        is_observed_api_request = False
    if is_observed_api_request:
        duration_ms = max(0, (time.monotonic_ns() - started_at) // 1_000_000)
        route = request.scope.get("route")
        normalized_path = getattr(route, "path", "/unmatched")
        if not isinstance(normalized_path, str) or len(normalized_path) > 2048:
            normalized_path = "/unmatched"
        idempotency_outcome = getattr(request.state, "idempotency_outcome", "not_used")
        request_outcome = getattr(request.state, "outcome", None)
        if request_outcome is None:
            request_outcome = {
                "created": "payment_created",
                "replayed": "idempotency_replay",
                "payload_mismatch": "payload_conflict",
            }.get(
                idempotency_outcome,
                "validation_error"
                if response.status_code == 422
                else "payload_conflict"
                if response.status_code == 409
                else "success"
                if response.status_code < 400
                else "handled_error",
            )

        def persist_request_log() -> None:
            with SessionLocal() as session:
                session.add(
                    RequestLog(
                        request_id=request_id,
                        request_method=request.method.upper(),
                        api_path=normalized_path,
                        http_status_code=response.status_code,
                        processing_duration_ms=duration_ms,
                        idempotency_outcome=getattr(
                            request.state, "idempotency_outcome", "not_used"
                        ),
                        outcome=request_outcome,
                        payment_id=getattr(request.state, "internal_payment_id", None),
                        sanitized_error_code=getattr(
                            request.state, "sanitized_error_code", None
                        ),
                    )
                )
                session.commit()

        try:
            await run_in_threadpool(persist_request_log)
        except Exception as error:
            logger.error(
                "Could not persist request log (request_id=%s, error_type=%s)",
                request_id,
                type(error).__name__,
            )

    return response


@app.get("/health/live", tags=["health"])
def live_check() -> dict[str, Literal["alive"]]:
    return {"status": "alive"}


@app.get("/health", tags=["health"], summary="Check API liveness")
def health_check() -> dict[str, Literal["alive"]]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def ready_check(request: Request) -> dict[str, Literal["ready", "connected"]]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        logger.error(
            "Database readiness check failed (request_id=%s, error_type=%s)",
            request.state.request_id,
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "database_unavailable",
                "message": "The database is temporarily unavailable.",
            },
        ) from error

    return {"status": "ready", "database": "connected"}
