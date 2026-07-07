from __future__ import annotations

import importlib.metadata as metadata

import pytest
from ibis_dune import Backend, __version__
from ibis_dune.compiler import DuneCompiler
from ibis_dune.ops import raw_predicate

from tests.helpers import bound_table
from tests.tables import RENTED_DB, RENTED_TABLE, scalar_constants


def test_package_version() -> None:
    assert __version__ == "0.1.1"
    assert metadata.version("ibis-dune") == "0.1.1"


def test_backend_name() -> None:
    assert Backend.name == "dune"


def test_ibis_backends_entry_point_registered() -> None:
    names = {ep.name for ep in metadata.entry_points(group="ibis.backends")}
    assert "dune" in names


def test_ibis_backends_entry_point_targets_ibis_dune() -> None:
    (ep,) = (
        e for e in metadata.entry_points(group="ibis.backends") if e.name == "dune"
    )
    assert ep.value == "ibis_dune"
    module = ep.load()
    assert module.Backend is Backend


def test_force_api_sets_uses_api(offline_backend: Backend) -> None:
    assert offline_backend.uses_api is False
    backend = Backend().connect(dune_api_key="offline-test-key", force_api=True)
    assert backend.uses_api is True


def test_ibis_dune_connect() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    assert backend.name == "dune"
    assert backend.dune_api_key == "offline-test-key"


def test_reset_to_trino_clears_use_api_flag(offline_backend: Backend) -> None:
    offline_backend._use_api = True
    offline_backend.reset_to_trino()
    assert offline_backend._use_api is False


def test_backend_exposes_compiler(offline_backend: Backend) -> None:
    assert offline_backend.name == "dune"
    assert isinstance(offline_backend.compiler, DuneCompiler)
    assert offline_backend.uses_api is False


def test_raw_predicate_compiles_on_backend(offline_backend: Backend) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB)
    compiled = t.filter(raw_predicate("1=1")).limit(1).compile()
    assert "1 = 1" in compiled
    assert isinstance(offline_backend.compiler, DuneCompiler)


@pytest.mark.integration
def test_get_schema_rented(dune_backend: Backend) -> None:
    schema = dune_backend.get_schema(RENTED_TABLE, database=RENTED_DB)
    assert len(schema) > 0
    assert "rentaltokenid" in schema
    assert "contract_address" in schema


@pytest.mark.integration
def test_sql_infers_schema(dune_backend: Backend) -> None:
    t = scalar_constants(dune_backend)
    assert "n" in t.schema()
    out = t.execute()
    assert int(out["n"].iloc[0]) == 42


@pytest.mark.integration
def test_free_tier_sql_flips_to_api(free_tier_backend: Backend) -> None:
    """Schema-less ``sql().execute()`` on free-tier keys must flip to REST."""
    assert free_tier_backend._use_api is False
    t = free_tier_backend.sql("SELECT CAST(1 AS BIGINT) AS n")
    out = t.execute()
    if not free_tier_backend._use_api:
        pytest.skip("Trino tier available; not a free-tier key")
    assert free_tier_backend.uses_api is True
    assert int(out["n"].iloc[0]) == 1
