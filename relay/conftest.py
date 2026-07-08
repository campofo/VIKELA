"""Pytest fixtures for the relay. Located at relay/ so `import relay` works."""

import pytest
from fastapi.testclient import TestClient

from relay import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
