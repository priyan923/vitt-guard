import os

import pytest

os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:5173"


@pytest.fixture(autouse=True)
def isolate_integration_database(request: pytest.FixtureRequest):
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    from sqlalchemy import delete, select
    from sqlalchemy.engine import make_url

    from app.core.settings import settings
    from app.db.session import SessionLocal
    from app.models.payment import IdempotencyRecord, Payment, RequestLog

    database_name = make_url(settings.database_url).database
    if database_name is None or not database_name.endswith("_test"):
        pytest.fail("Integration tests require a dedicated database ending in '_test'.")

    models = (Payment, IdempotencyRecord, RequestLog)
    with SessionLocal() as session:
        baseline_ids = {
            model: set(session.scalars(select(model.id))) for model in models
        }
    if any(baseline_ids.values()):
        pytest.fail(
            "Integration tests require empty payment, idempotency, and request-log "
            "tables; existing rows were left untouched."
        )

    try:
        yield
    finally:
        with SessionLocal() as session:
            for model in (RequestLog, IdempotencyRecord, Payment):
                created_ids = set(session.scalars(select(model.id))) - baseline_ids[model]
                if created_ids:
                    session.execute(delete(model).where(model.id.in_(created_ids)))
            session.commit()


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test_user:test_password@localhost/vitt_guard_test",
)
