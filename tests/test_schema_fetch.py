from __future__ import annotations

from unittest.mock import patch

import ibis
import pytest
import trino
from ibis.common.exceptions import TableNotFound
from ibis_dune import Backend
from ibis_dune.exceptions import DuneQueryError
from ibis_dune.schema_fetch import (
    INFORMATION_SCHEMA_COLUMNS_SCHEMA,
    SchemaFetchMixin,
)


@pytest.mark.integration
def test_information_schema_columns_schema_matches_dune(dune_backend: Backend) -> None:
    """Hardcoded ``information_schema.columns`` layout must match live Dune (LIMIT 0 probe)."""
    qualified = '"information_schema"."columns"'
    if dune_backend.uses_api:
        live = dune_backend._schema_from_api_limit0(f"SELECT * FROM {qualified}")
    else:
        live = dune_backend._schema_from_trino_limit0(qualified)

    expected = INFORMATION_SCHEMA_COLUMNS_SCHEMA
    assert (
        list(live.names) == list(expected.names)
    ), f"column name mismatch\nlive: {list(live.names)}\nexpected: {list(expected.names)}"
    live_sig = {n: str(d.copy(nullable=True)) for n, d in live.items()}
    exp_sig = {n: str(d.copy(nullable=True)) for n, d in expected.items()}
    assert live_sig == exp_sig, f"dtype mismatch\nlive: {live_sig}\nexpected: {exp_sig}"


def test_normalize_api_column_name_strips_sql_quotes() -> None:
    assert SchemaFetchMixin._normalize_api_column_name('"block_time"') == "block_time"
    assert SchemaFetchMixin._normalize_api_column_name("from") == "from"
    assert SchemaFetchMixin._normalize_api_column_name('"type"') == "type"
    assert SchemaFetchMixin._normalize_api_column_name("block_hash") == "block_hash"


def test_normalize_schema_strips_quoted_column_names() -> None:
    raw = ibis.schema(
        {
            '"block_time"': "timestamp(3)",
            "from": "binary",
            '"type"': "string",
        }
    )
    fixed = SchemaFetchMixin._normalize_schema(raw)
    assert list(fixed.names) == ["block_time", "from", "type"]


def _trino_user_error(
    *, error_name: str, message: str
) -> trino.exceptions.TrinoUserError:
    return trino.exceptions.TrinoUserError(
        {
            "message": message,
            "errorCode": 1,
            "errorName": error_name,
            "errorType": "USER_ERROR",
        },
        query_id="q-schema",
    )


def test_is_not_found_error_matches_trino_error_name() -> None:
    exc = _trino_user_error(
        error_name="TABLE_NOT_FOUND",
        message="line 1:1: Table 'foo.bar' does not exist",
    )
    assert SchemaFetchMixin._is_not_found_error(exc) is True


def test_is_not_found_error_rejects_non_not_found_user_error() -> None:
    exc = _trino_user_error(
        error_name="COLUMN_NOT_FOUND",
        message="line 1:1: Column cannot be resolved",
    )
    assert SchemaFetchMixin._is_not_found_error(exc) is False


def test_is_not_found_error_matches_dune_query_error_message() -> None:
    exc = DuneQueryError(message="line 1:15: Table 'dune.foo.bar' does not exist")
    assert SchemaFetchMixin._is_not_found_error(exc) is True


def test_get_schema_trino_missing_table_raises_table_not_found() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    not_found = _trino_user_error(
        error_name="TABLE_NOT_FOUND",
        message="line 1:1: Table 'x.y' does not exist",
    )
    with (
        patch.object(
            backend, "_schema_from_information_schema", return_value=ibis.schema({})
        ),
        patch.object(backend, "_schema_from_trino_limit0", side_effect=not_found),
    ):
        with pytest.raises(TableNotFound):
            backend.get_schema("missing_table", database="missing_db")


def test_get_schema_trino_non_not_found_raises_dune_query_error() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    not_found = _trino_user_error(
        error_name="COLUMN_NOT_FOUND",
        message="line 1:1: Column cannot be resolved",
    )
    with (
        patch.object(
            backend, "_schema_from_information_schema", return_value=ibis.schema({})
        ),
        patch.object(backend, "_schema_from_trino_limit0", side_effect=not_found),
    ):
        with pytest.raises(DuneQueryError):
            backend.get_schema("table_name", database="db_name")


def test_get_schema_rest_missing_table_raises_table_not_found() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key", force_api=True)
    with (
        patch.object(
            backend, "_schema_from_information_schema", return_value=ibis.schema({})
        ),
        patch.object(
            backend,
            "_schema_from_api_limit0",
            side_effect=DuneQueryError(
                message="line 1:18: Table 'dune.foo.bar' does not exist"
            ),
        ),
    ):
        with pytest.raises(TableNotFound):
            backend.get_schema("missing_table", database="foo")


def test_get_schema_rest_non_not_found_raises_dune_query_error() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key", force_api=True)
    with (
        patch.object(
            backend, "_schema_from_information_schema", return_value=ibis.schema({})
        ),
        patch.object(
            backend,
            "_schema_from_api_limit0",
            side_effect=DuneQueryError(message="line 1:7: mismatched input"),
        ),
    ):
        with pytest.raises(DuneQueryError):
            backend.get_schema("some_table", database="foo")


def _tier_error() -> trino.exceptions.TrinoUserError:
    return _trino_user_error(
        error_name="INVALID_PERFORMANCE_TIER",
        message="Invalid performance tier: large",
    )


def test_infer_schema_for_sql_tier_error_flips_to_api() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    expected = ibis.schema({"n": "int64"})
    tier = _tier_error()

    class FakeCursor:
        def execute(self, _sql: str) -> None:
            raise tier

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with (
        patch.object(backend, "begin", return_value=FakeCursor()),
        patch.object(
            backend, "_schema_from_api_limit0", return_value=expected
        ) as mock_api,
    ):
        schema = backend._infer_schema_for_sql("SELECT CAST(1 AS BIGINT) AS n")

    mock_api.assert_called_once_with("SELECT CAST(1 AS BIGINT) AS n")
    assert backend._use_api is True
    assert schema == expected


def test_get_schema_trino_tier_error_flips_to_api() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    expected = ibis.schema({"id": "int64"})
    tier = _tier_error()

    with (
        patch.object(
            backend, "_schema_from_information_schema", return_value=ibis.schema({})
        ),
        patch.object(backend, "_schema_from_trino_limit0", side_effect=tier),
        patch.object(
            backend, "_schema_from_api_limit0", return_value=expected
        ) as mock_api,
    ):
        schema = backend.get_schema("some_table", database="foo")

    mock_api.assert_called_once_with('SELECT * FROM "foo"."some_table"')
    assert backend._use_api is True
    assert schema == expected


def test_schema_from_trino_limit0_tier_error_flips_to_api() -> None:
    backend = Backend().connect(dune_api_key="offline-test-key")
    expected = ibis.schema({"id": "int64"})
    tier = _tier_error()

    class FakeCursor:
        def execute(self, _sql: str) -> None:
            raise tier

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with (
        patch.object(backend, "begin", return_value=FakeCursor()),
        patch.object(
            backend, "_schema_from_api_limit0", return_value=expected
        ) as mock_api,
    ):
        schema = backend._schema_from_trino_limit0('"foo"."bar"')

    mock_api.assert_called_once_with('SELECT * FROM "foo"."bar"')
    assert backend._use_api is True
    assert schema == expected
