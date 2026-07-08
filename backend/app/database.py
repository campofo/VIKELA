"""SQLite engine and session management for the VIKELA backend."""

import os
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DB_PATH = os.environ.get("VIKELA_DB_PATH", "vikela.db")

# check_same_thread=False lets the connection be shared across FastAPI's thread
# pool; SQLite is fine with this for our low write volume.
engine = create_engine(
    "sqlite:///{}".format(DB_PATH),
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record):
    # WAL gives better read/write concurrency for a long-running server, and
    # foreign_keys=ON enforces the FK columns declared in models.py (SQLite
    # leaves them off by default).
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db():
    """Create the database file (and parent dir) and all tables if missing."""
    parent = Path(DB_PATH).resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    # Import models so SQLModel.metadata knows about every table before create.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency yielding a database session."""
    with Session(engine) as session:
        yield session
