from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings

connect_args: dict[str, int | str] = {
    "connect_timeout": 5,
    "options": "-c statement_timeout=10000 -c lock_timeout=5000",
}
if settings.app_env == "production":
    connect_args["sslmode"] = "require"

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_timeout=5,
    pool_recycle=1_800,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Session:
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
