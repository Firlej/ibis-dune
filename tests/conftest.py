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
def dune_api_key_free() -> str:
    key = os.environ.get("DUNE_API_KEY_FREE")
    if not key:
        pytest.skip("DUNE_API_KEY_FREE not set")
    return key


@pytest.fixture(scope="session")
def free_tier_backend(dune_api_key_free: str) -> Backend:
    """Backend connected with a free-tier key (no Trino)."""
    return Backend().connect(dune_api_key=dune_api_key_free)
