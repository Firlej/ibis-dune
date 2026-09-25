from __future__ import annotations

from unittest.mock import patch

import pytest
import trino
from ibis.backends.sql import SQLBackend
from ibis_dune import Backend
from ibis_dune.exceptions import DuneQueryError

from tests.helpers import bound_table
from tests.tables import RENTED_DB, RENTED_TABLE


def _trino_query_error(
    *, message: str = "line 1:1: Table not found"
) -> trino.exceptions.TrinoQueryError:
    return trino.exceptions.TrinoQueryError(
        {
            "message": message,
            "errorCode": 46,
            "errorName": "TABLE_NOT_FOUND",
            "errorType": "USER_ERROR",
        },
        query_id="q-test",
    )


def _trino_user_error(
    *, message: str = "line 1:1: Column cannot be resolved"
) -> trino.exceptions.TrinoUserError:
    return trino.exceptions.TrinoUserError(
        {
            "message": message,
            "errorCode": 47,
            "errorName": "COLUMN_NOT_FOUND",
            "errorType": "USER_ERROR",
        },
        query_id="q-user",
    )


def test_execute_raises_dune_query_error_on_trino_query_error(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    query_error = _trino_query_error()

    with patch.object(SQLBackend, "execute", side_effect=query_error):
        with pytest.raises(DuneQueryError) as exc_info:
            t.execute()

    assert exc_info.value.message == "line 1:1: Table not found"
    assert exc_info.value.query_id == "q-test"
    assert isinstance(exc_info.value.original, trino.exceptions.TrinoQueryError)


def test_execute_raises_dune_query_error_on_http_error(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    http_error = trino.exceptions.HttpError("error 500")

    with patch.object(SQLBackend, "execute", side_effect=http_error):
        with pytest.raises(DuneQueryError) as exc_info:
            t.execute()

    assert "error 500" in exc_info.value.message
    assert isinstance(exc_info.value.original, trino.exceptions.HttpError)


def test_execute_raises_dune_query_error_on_trino_user_error(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    user_error = _trino_user_error()

    with patch.object(SQLBackend, "execute", side_effect=user_error):
        with pytest.raises(DuneQueryError) as exc_info:
            t.execute()

    assert exc_info.value.query_id == "q-user"
    assert isinstance(exc_info.value.original, trino.exceptions.TrinoUserError)


def test_execute_invalid_performance_tier_requires_paid_trino(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    tier = _trino_user_error(message="Invalid performance tier: large")

    with patch.object(SQLBackend, "execute", side_effect=tier):
        with pytest.raises(DuneQueryError) as exc_info:
            t.execute()

    assert "paid API plan" in exc_info.value.message
    assert "Invalid performance tier" in exc_info.value.message
    assert isinstance(exc_info.value.original, trino.exceptions.TrinoUserError)


def test_cursor_batches_raises_dune_query_error(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    query_error = _trino_query_error(message="line 1:1: Syntax error")

    with patch.object(SQLBackend, "_cursor_batches", side_effect=query_error):
        with pytest.raises(DuneQueryError) as exc_info:
            list(offline_backend._cursor_batches(t, chunk_size=10))

    assert exc_info.value.message == "line 1:1: Syntax error"
    assert exc_info.value.query_id == "q-test"


def test_to_dune_query_error_helper() -> None:
    query_error = _trino_query_error()
    wrapped = Backend._to_dune_query_error(query_error)
    assert wrapped.message == query_error.message
    assert wrapped.query_id == "q-test"
    assert wrapped.original is query_error

    http_error = trino.exceptions.HttpError("error 405")
    wrapped_http = Backend._to_dune_query_error(http_error)
    assert wrapped_http.message == "error 405"
    assert wrapped_http.original is http_error

    with pytest.raises(TypeError):
        Backend._to_dune_query_error(ValueError("nope"))


def test_execute_auth_error_includes_api_key_hint(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    auth_error = _trino_query_error(message="401 Unauthorized: invalid api key")

    with patch.object(SQLBackend, "execute", side_effect=auth_error):
        with pytest.raises(DuneQueryError) as exc_info:
            t.execute()

    assert "check dune_api_key" in exc_info.value.message
