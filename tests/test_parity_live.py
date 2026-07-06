"""Live Trino vs REST parity tests (strict comparison, no backend fixes in Phase A)."""

from __future__ import annotations

import pytest

from tests.parity_helpers import (
    assert_all_columns_rendered,
    assert_execute_parity,
    assert_preview_parity,
    assert_pyarrow_parity,
    assert_schema_parity,
    assert_sql_infer_schema_parity,
)
from tests.tables import (
    PARITY_BUILDERS,
    RENTED_DB,
    RENTED_RENTALTOKENID,
    RENTED_TABLE,
    rented_one_row,
)

_SCALAR_INNER_SQL = (
    "SELECT CAST(42 AS BIGINT) AS n, CAST(1.5 AS DOUBLE) AS f, "
    "TIMESTAMP '2024-01-01 00:00:00' AS ts, 'x' AS s "
    "ORDER BY n"
)


@pytest.mark.trino
@pytest.mark.parametrize("name", list(PARITY_BUILDERS))
def test_execute_parity(name: str, trino_backend, api_backend) -> None:
    """``execute()`` must match exactly (dtypes, values, row order)."""
    assert_execute_parity(trino_backend, api_backend, PARITY_BUILDERS[name])


@pytest.mark.trino
@pytest.mark.parametrize("name", ["rented_one_row", "logs_data_sample"])
def test_pyarrow_parity(name: str, trino_backend, api_backend) -> None:
    """``to_pyarrow()`` must match exactly."""
    assert_pyarrow_parity(trino_backend, api_backend, PARITY_BUILDERS[name])


@pytest.mark.trino
def test_schema_parity_rented(trino_backend, api_backend) -> None:
    """``get_schema`` for ``enterprise_evt_rented`` must agree."""
    assert_schema_parity(trino_backend, api_backend, RENTED_TABLE, RENTED_DB)


@pytest.mark.trino
def test_sql_infer_schema_parity(trino_backend, api_backend) -> None:
    """``_infer_schema_for_sql`` must agree for scalar ``sql()``."""
    assert_sql_infer_schema_parity(trino_backend, api_backend, _SCALAR_INNER_SQL)


@pytest.mark.trino
def test_preview_parity_rented_one_row(trino_backend, api_backend) -> None:
    """Rich preview text must match for the single-row rented query."""
    assert_preview_parity(trino_backend, api_backend, rented_one_row)


@pytest.mark.trino
def test_all_columns_rendered_rented_one_row(trino_backend) -> None:
    """All rented columns must render without a trailing ``…`` column."""
    assert_all_columns_rendered(rented_one_row(trino_backend))


@pytest.mark.trino
def test_rentaltokenid_value(trino_backend) -> None:
    """Sanity: Trino returns the known uint256 ``rentaltokenid`` constant."""
    df = rented_one_row(trino_backend).execute()
    assert len(df) == 1
    assert int(df["rentaltokenid"].iloc[0]) == RENTED_RENTALTOKENID
