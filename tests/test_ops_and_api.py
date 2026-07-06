from __future__ import annotations

import logging

import pytest
from ibis import to_sql
from ibis_dune import Backend
from ibis_dune.exceptions import DuneResultTooLargeError
from ibis_dune.ops import hex_literal

from tests.helpers import bound_table
from tests.tables import (
    RENTED_CONTRACT,
    RENTED_DB,
    RENTED_TABLE,
    rented_raw_predicate,
    rented_raw_scalar,
    rented_sample,
)


def test_hex_literal_compiles_to_dune_hex_string(offline_backend: Backend) -> None:
    from ibis import _

    t = (
        bound_table(offline_backend, RENTED_TABLE, RENTED_DB)
        .filter(_.contract_address == hex_literal(RENTED_CONTRACT))
        .limit(1)
    )
    sql = str(to_sql(t))
    assert RENTED_CONTRACT.lower() in sql.lower()


def test_hex_literal_accepts_empty_and_prefixed_hex() -> None:
    assert repr(hex_literal("0x")) == "0x"
    assert repr(hex_literal("0xab")) == "0xab"


def test_hex_literal_rejects_malformed_hex() -> None:
    with pytest.raises(ValueError, match="invalid hex literal"):
        hex_literal("0xgg")
    with pytest.raises(ValueError, match="invalid hex literal"):
        hex_literal("abc")


@pytest.mark.integration
def test_raw_predicate_compiles_and_executes(dune_backend: Backend) -> None:
    t = rented_raw_predicate(dune_backend)
    sql = str(to_sql(t))
    assert RENTED_CONTRACT.lower() in sql.lower()
    assert f'"{RENTED_DB}"."{RENTED_TABLE}"' in sql
    assert t.execute().shape == (2, 23)


@pytest.mark.integration
def test_raw_scalar_compiles_and_executes(dune_backend: Backend) -> None:
    t = rented_raw_scalar(dune_backend)
    sql = str(to_sql(t))
    assert "cast(42 as bigint)" in sql.lower()
    row = t.execute()
    assert row.shape == (1, 2)
    assert int(row["probe"].iloc[0]) == 42


@pytest.mark.integration
def test_execute_via_api_warns_when_result_exceeds_warning_threshold(
    dune_api_key: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = Backend().connect(
        dune_api_key=dune_api_key,
        force_api=True,
        dune_api_warning_bytes=10,
        dune_api_max_bytes=4 * 1024 * 1024 * 1024,
    )
    with caplog.at_level(logging.WARNING):
        rented_sample(backend).to_pandas()

    assert any("dune_api_warning_bytes" in record.message for record in caplog.records)


@pytest.mark.integration
def test_execute_via_api_raises_when_result_exceeds_max_bytes(
    limits_backend: Backend,
) -> None:
    with pytest.raises(DuneResultTooLargeError) as exc_info:
        rented_sample(limits_backend).to_pandas()

    err = exc_info.value
    assert err.total_bytes > err.max_bytes == 10


@pytest.mark.integration
def test_execute_via_api_within_limits(api_backend: Backend) -> None:
    df = rented_sample(api_backend).to_pandas()
    assert len(df) == 5
