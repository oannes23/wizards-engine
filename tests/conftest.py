"""Shared pytest fixtures for the Wizards Engine test suite.

Provides function-scoped fixtures for a fully isolated in-memory SQLite
database, a FastAPI TestClient wired to that database, pre-populated seed
data, and a helper for authenticating requests as any test user.

Fixtures
--------
db_engine
    Creates an in-memory SQLite engine with StaticPool (so the TestClient
    worker thread shares the same connection).  All tables are created at
    engine creation and dropped on teardown.  Function-scoped — each test
    gets a completely isolated engine.  Usually you want ``db`` instead.

db
    Function-scoped.  Creates a fresh set of tables on a new in-memory
    engine and yields an open Session.  Each test gets a completely
    isolated database.

client
    Function-scoped.  Builds a TestClient that shares the same engine as
    the ``db`` fixture.  ``get_db`` is overridden so every request uses the
    isolated test database.

seed_data
    Function-scoped.  Calls ``fixtures.seed_data(db)`` against the current
    test's ``db`` session and returns the resulting reference dict.

Usage example::

    def test_something(client, seed_data):
        gm = seed_data["gm"]
        auth_as(client, gm)
        response = client.get("/api/v1/me")
        assert response.status_code == 200
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wizards_engine.api.auth import COOKIE_NAME
from wizards_engine.app import create_app
from wizards_engine.db import get_db
from wizards_engine.models.base import Base
from wizards_engine.models.user import User

from tests.fixtures import seed_data as _seed_data_fn


# ---------------------------------------------------------------------------
# Helpers — importable by test modules
# ---------------------------------------------------------------------------


def auth_as(client: TestClient, user: User) -> None:
    """Set the auth cookie on *client* so subsequent requests are authenticated.

    Mutates the client's cookie jar in-place.  Calling this again with a
    different user replaces the previous cookie.

    Args:
        client: The TestClient instance to authenticate.
        user: The User whose ``login_code`` should be used as the cookie value.
    """
    client.cookies.set(COOKIE_NAME, user.login_code)


# ---------------------------------------------------------------------------
# db_engine — one in-memory engine per test (function scope)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    """Provide an in-memory SQLite engine with all tables created.

    Uses StaticPool so that the TestClient's ASGI worker thread and the main
    test thread share the same in-memory database connection.

    Yields:
        A SQLAlchemy Engine.  Tables are dropped and the engine is disposed
        on teardown.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# db — one Session per test, bound to a fresh engine
# ---------------------------------------------------------------------------


@pytest.fixture
def db(db_engine) -> Session:
    """Provide an open SQLAlchemy Session bound to the isolated test engine.

    The session is closed on teardown.  Commits made during the test are
    visible to subsequent queries within the same session (and to the
    TestClient, since both use the same in-memory engine via StaticPool).

    Yields:
        An open SQLAlchemy Session.
    """
    TestSessionLocal = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False
    )
    session: Session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# client — TestClient wired to the same engine as db
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_engine) -> TestClient:
    """Provide a TestClient backed by the isolated test database.

    ``get_db`` is overridden so every HTTP request in the test uses the
    same in-memory SQLite engine as the ``db`` fixture.  Uses the real
    ``create_app()`` factory so the custom HTTPException handler is active.

    Yields:
        A Starlette TestClient (synchronous).
    """
    TestSessionLocal = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False
    )

    def _get_test_db():
        session: Session = TestSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = _get_test_db

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# seed_data — canonical seed data populated into the test db
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_data(db) -> dict:
    """Populate the test database with canonical seed data.

    Calls :func:`tests.fixtures.seed_data` against the current test's ``db``
    session and returns the reference dict so tests can look up specific
    entities by role/name.

    Depends on the ``db`` fixture — requesting ``seed_data`` implicitly
    brings in ``db`` (and its underlying ``db_engine``).

    Returns:
        A dict with keys: ``gm``, ``player1``, ``player2``, ``player3``,
        ``pc1``, ``pc2``, ``pc3``, ``npc1``, ``npc2``, ``group``,
        ``region``, ``district``, ``pc1_bond``, ``pc2_bond``,
        ``npc1_bond``, ``npc2_bond``.
    """
    return _seed_data_fn(db)
