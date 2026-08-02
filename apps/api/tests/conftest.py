"""API test fixtures: app with safe test settings (no external services)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from oeop_api.main import create_app
from oeop_core.settings import Settings

#: Azurite's documented development credential (public knowledge, not a secret).
AZURITE_CONN = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",  # skips ensure_container/ensure_queues at startup
        database_url="postgresql+asyncpg://oeop:oeop_local_dev@localhost:5432/oeop",
        storage_connection_string=AZURITE_CONN,
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
