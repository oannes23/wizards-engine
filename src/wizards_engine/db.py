"""Database engine, session factory, and FastAPI dependency for Wizards Engine.

Uses synchronous SQLAlchemy (not async) — SQLite does not benefit from async I/O
and the sync API is simpler to reason about and test.

Database file path is read from the WIZARDS_DB_PATH environment variable, falling
back to ``wizards_engine.db`` in the current working directory when unset.
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = "wizards_engine.db"

_db_path = os.environ.get("WIZARDS_DB_PATH", _DEFAULT_DB_PATH)
DATABASE_URL = f"sqlite:///{_db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Enable FK enforcement and WAL journal mode on every new connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_db():
    """Yield a scoped SQLAlchemy session for use as a FastAPI dependency.

    Commits on success, rolls back on unhandled exception, and always closes
    the session when the request finishes.

    Usage::

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
