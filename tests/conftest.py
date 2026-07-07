"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from ibis_dune import Backend

_ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(_ENV_FILE)


def _api_key() -> str | None:
    return os.environ.get("DUNE_API_KEY")


@pytest.fixture
def offline_backend() -> Backend:
    """Connected backend for offline unit tests (no queries executed)."""
    return Backend().connect(dune_api_key="offline-test-key")


@pytest.fixture(scope="session")
def dune_api_key() -> str:
    key = _api_key()
    if not key:
        pytest.skip("DUNE_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def dune_backend(dune_api_key: str) -> Backend:
    return Backend().connect(dune_api_key=dune_api_key)


@pytest.fixture(scope="session")
def api_backend(dune_api_key: str) -> Backend:
    return Backend().connect(dune_api_key=dune_api_key, force_api=True)


@pytest.fixture(scope="session")
def limits_backend(dune_api_key: str) -> Backend:
    return Backend().connect(
        dune_api_key=dune_api_key,
        force_api=True,
        dune_api_warning_bytes=10,
        dune_api_max_bytes=10,
    )


@pytest.fixture(scope="session")
def trino_backend(dune_backend: Backend) -> Backend:
    """Return a Trino-connected backend; skip if tier fallback flipped to REST."""
    dune_backend.sql("SELECT CAST(1 AS BIGINT) AS n").execute()
    if dune_backend._use_api:
        pytest.skip("Trino tier unavailable; backend fell back to REST")
    return dune_backend


@pytest.fixture(scope="session")
def free_tier_backend(dune_api_key: str) -> Backend:
    """Return a backend for free-tier keys that lack Trino access."""
    return Backend().connect(dune_api_key=dune_api_key)
