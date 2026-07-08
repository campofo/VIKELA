"""SQLite engine and session management for the VIKELA backend."""

import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = os.environ.get("VIKELA_DB_PATH", "vikela.db")

# check_same_thread=False lets the connection be shared across FastAPI's thread
# pool; SQLite is fine with this for our low write volume.
engine = create_engine(
    "sqlite:///{}".format(DB_PATH),
    echo=False,
    connect_args={"check_same_thread": False},
)


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
