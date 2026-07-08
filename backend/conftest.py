"""Pytest fixtures: isolated temp SQLite DB + FastAPI TestClient.

Located at backend/ so this directory is on sys.path (making `app` importable)
and so the DB path is set before app.database builds its engine.
"""

import os
import tempfile

# Point the backend at a throwaway DB before app.database imports and creates the
# engine at module load. Must happen before importing anything from app.
os.environ["VIKELA_DB_PATH"] = os.path.join(tempfile.gettempdir(), "vikela_test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    # Fresh schema per test for isolation.
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
