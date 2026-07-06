"""Offline parity replay via raw REST boundary mocks and Trino goldens."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from ibis_dune import Backend
from ibis_dune.schema_fetch import INFORMATION_SCHEMA_COLUMNS_SCHEMA

from tests.capture_parity_fixtures import (
    load_rest_raw_fixture,
    load_schema_fixture,
    load_trino_execute_fixture,
    load_trino_pyarrow_fixture,
)
from tests.tables import LOGS_DB, LOGS_TABLE, PARITY_BUILDERS, RENTED_DB, RENTED_TABLE


@pytest.fixture
def mock_api_backend(offline_backend: Backend) -> Backend:
    """Offline backend with ``force_api=True`` for REST execute replay."""
    return Backend().connect(dune_api_key="offline-test-key", force_api=True)


def _schema_patches(name: str):
    """Return patched ``get_schema`` / ``_infer_schema_for_sql`` for offline builders."""

    def patched_get_schema(self, table_name, *, catalog=None, database=None):
        if table_name == "columns" and database == "information_schema":
            return INFORMATION_SCHEMA_COLUMNS_SCHEMA
        if table_name == RENTED_TABLE and database == RENTED_DB:
            return load_schema_fixture("rented_table")
        if table_name == LOGS_TABLE and database == LOGS_DB:
            return load_schema_fixture("logs_table")
        raise AssertionError(
            f"unexpected get_schema({table_name!r}, database={database!r}) in parity mock"
        )

    def patched_infer_schema(self, inner_sql: str):
        return load_schema_fixture(name)

    return patched_get_schema, patched_infer_schema


@pytest.mark.parity_mock
@pytest.mark.parametrize("name", list(PARITY_BUILDERS))
def test_execute_parity_mocked(name: str, mock_api_backend: Backend) -> None:
    """Run real REST coercion on captured raw rows; compare to Trino execute golden."""
    rest_raw = load_rest_raw_fixture(name)
    trino_golden = load_trino_execute_fixture(name)
    build = PARITY_BUILDERS[name]
    patched_get_schema, patched_infer_schema = _schema_patches(name)

    def patched_execute_sql(self, sql: str):
        return rest_raw["rows"], rest_raw["column_names"]

    with (
        patch.object(Backend, "_execute_sql_via_api", patched_execute_sql),
        patch.object(Backend, "get_schema", patched_get_schema),
        patch.object(Backend, "_infer_schema_for_sql", patched_infer_schema),
    ):
        api_df = build(mock_api_backend).execute()

    pd.testing.assert_frame_equal(api_df, trino_golden, check_dtype=True)


@pytest.mark.parity_mock
@pytest.mark.parametrize("name", ["rented_one_row", "logs_data_sample"])
def test_pyarrow_parity_mocked(name: str, mock_api_backend: Backend) -> None:
    """Run real REST pyarrow path on captured raw rows; compare to Trino golden."""
    rest_raw = load_rest_raw_fixture(name)
    trino_golden = load_trino_pyarrow_fixture(name)
    build = PARITY_BUILDERS[name]
    patched_get_schema, patched_infer_schema = _schema_patches(name)

    def patched_execute_sql(self, sql: str):
        return rest_raw["rows"], rest_raw["column_names"]

    with (
        patch.object(Backend, "_execute_sql_via_api", patched_execute_sql),
        patch.object(Backend, "get_schema", patched_get_schema),
        patch.object(Backend, "_infer_schema_for_sql", patched_infer_schema),
    ):
        api_arrow = build(mock_api_backend).to_pyarrow()

    assert api_arrow.equals(trino_golden), (
        f"PyArrow mismatch\nTrino schema: {trino_golden.schema}\n"
        f"REST schema:  {api_arrow.schema}\n"
        f"Trino:\n{trino_golden.to_pandas().to_string()}\n"
        f"REST:\n{api_arrow.to_pandas().to_string()}"
    )
