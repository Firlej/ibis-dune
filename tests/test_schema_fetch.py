from __future__ import annotations

from unittest.mock import patch

import ibis
import pytest
import trino
from ibis.common.exceptions import TableNotFound
from ibis_dune import Backend
from ibis_dune.exceptions import DuneQueryError
from ibis_dune.schema_fetch import SchemaFetchMixin


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
