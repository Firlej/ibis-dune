from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import ibis
import ibis.expr.datatypes as dt
from ibis_dune import Backend
from ibis_dune.api_execution import ApiExecutionMixin

from tests.helpers import bound_table
from tests.tables import RENTED_DB, RENTED_TABLE


def test_value_for_pyarrow_decimal38_returns_decimal_not_str() -> None:
    dtype = dt.Decimal(precision=38, scale=0)
    out = ApiExecutionMixin._value_for_pyarrow("12345", dtype)
    assert isinstance(out, Decimal)
    assert out == Decimal("12345")


def test_value_for_pyarrow_decimal78_returns_str_for_string_arrow_type() -> None:
    dtype = dt.Decimal(precision=78, scale=0)
    out = ApiExecutionMixin._value_for_pyarrow("9488020000000", dtype)
    assert isinstance(out, str)
    assert out == "9488020000000"


def test_value_for_pyarrow_binary_matches_trino_hex_string_bytes() -> None:
    dtype = dt.binary
    assert ApiExecutionMixin._value_for_pyarrow("0x", dtype) == b"0x"
    assert ApiExecutionMixin._value_for_pyarrow("0xab", dtype) == b"0xab"
    assert ApiExecutionMixin._value_for_pyarrow(None, dtype) is None


def test_rest_rows_to_dataframe_aligns_camelcase_rest_columns() -> None:
    schema = ibis.schema(
        {
            "contract_address": dt.binary,
            "endtime": dt.int64,
            "gcfee": dt.Decimal(precision=78, scale=0),
        }
    )
    rows = [
        {
            "contract_address": "0x01",
            "endTime": 42,
            "gcFee": "99",
        }
    ]
    column_names = ["contract_address", "endTime", "gcFee"]
    df = ApiExecutionMixin._rest_rows_to_dataframe(
        rows, schema, column_names=column_names
    )
    assert int(df["endtime"].iloc[0]) == 42
    assert str(df["gcfee"].iloc[0]) == "99"
    assert df["contract_address"].iloc[0] == "0x01"


def test_execute_force_api_passes_limit_and_params_to_compile() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key", force_api=True)
    expr = bound_table(backend, RENTED_TABLE, RENTED_DB).limit(1)
    seen: dict[str, object] = {}

    def fake_compile(table, **kwargs):
        seen.update(kwargs)
        return "SELECT 1"

    with (
        patch.object(backend, "compile", side_effect=fake_compile),
        patch.object(
            backend,
            "_execute_sql_via_api",
            return_value=(
                [{"contract_address": "0x01", "evt_tx_hash": "0x02"}],
                ["contract_address", "evt_tx_hash"],
            ),
        ),
    ):
        backend.execute(expr, params={"ignored": 1}, limit=7)

    assert seen["limit"] == 7
    assert seen["params"] == {"ignored": 1}


def test_cursor_batches_force_api_passes_limit_and_params_to_compile() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key", force_api=True)
    expr = bound_table(backend, RENTED_TABLE, RENTED_DB).limit(1)
    seen: dict[str, object] = {}

    def fake_compile(table, **kwargs):
        seen.update(kwargs)
        return "SELECT 1"

    with (
        patch.object(backend, "compile", side_effect=fake_compile),
        patch.object(
            backend,
            "_execute_sql_via_api",
            return_value=(
                [{"contract_address": "0x01", "evt_tx_hash": "0x02"}],
                ["contract_address", "evt_tx_hash"],
            ),
        ),
    ):
        list(backend._cursor_batches(expr, params={"ignored": 1}, limit=11))

    assert seen["limit"] == 11
    assert seen["params"] == {"ignored": 1}
