from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
import trino
from dune_client.models import ExecutionState, QueryFailedError
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


def test_execute_falls_back_on_invalid_performance_tier_error(
    offline_backend: Backend,
) -> None:
    t = bound_table(offline_backend, RENTED_TABLE, RENTED_DB).limit(1)
    tier_error = _trino_user_error(message="Invalid performance tier: large")
    expected = pd.DataFrame(
        {"contract_address": ["0x1"], "evt_tx_hash": ["0x2"]},
    )

    with (
        patch.object(SQLBackend, "execute", side_effect=tier_error),
        patch.object(
            offline_backend,
            "_execute_expr_via_api",
            return_value=expected,
        ) as mock_api,
    ):
        result = t.execute()

    mock_api.assert_called_once()
    assert offline_backend._use_api is True
    assert result["contract_address"].iloc[0] == "0x1"


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


def test_execute_sql_first_page_wraps_query_failed_error(
    offline_backend: Backend,
) -> None:
    failed_status = SimpleNamespace(
        state=ExecutionState.FAILED,
        error=SimpleNamespace(message="Table does not exist"),
    )
    with (
        patch.object(
            offline_backend,
            "_call_dune_api",
            return_value=SimpleNamespace(execution_id="job-1"),
        ),
        patch.object(
            offline_backend, "_wait_for_execution", return_value=failed_status
        ),
    ):
        with pytest.raises(DuneQueryError) as exc_info:
            offline_backend._execute_sql_first_page("SELECT 1")

    assert "Table does not exist" in exc_info.value.message
    assert isinstance(exc_info.value.original, QueryFailedError)
