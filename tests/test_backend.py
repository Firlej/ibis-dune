from __future__ import annotations

import importlib.metadata as metadata

import ibis
import pytest
from ibis.expr.types.rich import to_rich
from ibis_dune import Backend, DuneQueryError, __version__
from ibis_dune.compiler import DuneCompiler
from ibis_dune.ops import raw_predicate
from rich.console import Console

from tests.helpers import bound_table
from tests.tables import (
    RENTED_DB,
    RENTED_RENTALTOKENID,
    RENTED_TABLE,
    rented_one_row,
    scalar_constants,
)


def test_package_version() -> None:
    assert __version__ == "0.2.0"
    assert metadata.version("ibis-dune") == "0.2.0"


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


def test_ibis_dune_connect() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    assert backend.name == "dune"
    assert backend.dune_api_key == "offline-test-key"


def test_backend_exposes_compiler(offline_backend: Backend) -> None:
    assert offline_backend.name == "dune"
    assert isinstance(offline_backend.compiler, DuneCompiler)


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
def test_contract_address_schema_is_binary(dune_backend: Backend) -> None:
    """Record rented ``contract_address`` dtypes from ``get_schema`` and schema-less ``sql()``."""
    table_schema = dune_backend.get_schema(RENTED_TABLE, database=RENTED_DB)
    inferred = dune_backend.sql(
        f'SELECT contract_address FROM "{RENTED_DB}"."{RENTED_TABLE}"'
    )
    assert table_schema["contract_address"].is_binary()
    assert inferred.schema()["contract_address"].is_string()


@pytest.mark.integration
def test_sql_infers_schema(dune_backend: Backend) -> None:
    t = scalar_constants(dune_backend)
    assert "n" in t.schema()
    out = t.execute()
    assert int(out["n"].iloc[0]) == 42


@pytest.mark.integration
def test_rentaltokenid_value(dune_backend: Backend) -> None:
    """Sanity: Trino returns the known uint256 ``rentaltokenid`` constant."""
    df = rented_one_row(dune_backend).execute()
    assert len(df) == 1
    assert int(df["rentaltokenid"].iloc[0]) == RENTED_RENTALTOKENID


@pytest.mark.integration
def test_all_columns_rendered_rented_one_row(dune_backend: Backend) -> None:
    """All rented columns must render without a trailing ``…`` column."""
    expr = rented_one_row(dune_backend)
    rich_table = to_rich(expr, max_columns=0, console_width=float("inf"))
    assert len(rich_table.columns) == len(expr.columns)
    console = Console(force_terminal=False, width=10_000)
    with console.capture() as capture:
        console.print(rich_table)
    text = capture.get().rstrip()
    for name in expr.columns:
        assert name in text, f"column {name!r} missing from preview:\n{text}"


@pytest.mark.integration
def test_free_key_sql_execute_requires_paid_trino(free_tier_backend: Backend) -> None:
    """Explicit schema so this hits ``execute``, not LIMIT 0 inference."""
    t = free_tier_backend.sql(
        "SELECT CAST(1 AS BIGINT) AS n",
        schema=ibis.schema({"n": "int64"}),
    )
    with pytest.raises(DuneQueryError) as exc_info:
        t.execute()
    assert "paid API plan" in exc_info.value.message


@pytest.mark.integration
def test_free_key_sql_schema_infer_requires_paid_trino(
    free_tier_backend: Backend,
) -> None:
    """Schema-less ``sql()`` hits Trino LIMIT 0 inference."""
    with pytest.raises(DuneQueryError) as exc_info:
        free_tier_backend.sql("SELECT CAST(1 AS BIGINT) AS n")
    assert "paid API plan" in exc_info.value.message


@pytest.mark.integration
def test_free_key_get_schema_requires_paid_trino(free_tier_backend: Backend) -> None:
    """``get_schema`` hits information_schema / LIMIT 0 on Trino (no table scan)."""
    with pytest.raises(DuneQueryError) as exc_info:
        free_tier_backend.get_schema(RENTED_TABLE, database=RENTED_DB)
    assert "paid API plan" in exc_info.value.message
