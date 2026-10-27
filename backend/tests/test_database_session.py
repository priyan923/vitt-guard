import pytest

from app.db import session as db_session


def test_database_session_rolls_back_and_closes_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SessionStub:
        rolled_back = False
        closed = False

        def __enter__(self) -> "SessionStub":
            return self

        def __exit__(self, *args: object) -> None:
            self.closed = True

        def rollback(self) -> None:
            self.rolled_back = True

    stub = SessionStub()
    monkeypatch.setattr(db_session, "SessionLocal", lambda: stub)
    dependency = db_session.get_db()

    assert next(dependency) is stub
    with pytest.raises(RuntimeError, match="injected request failure"):
        dependency.throw(RuntimeError("injected request failure"))

    assert stub.rolled_back
    assert stub.closed
