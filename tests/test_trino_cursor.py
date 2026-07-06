from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import trino
from ibis_dune import Backend


def test_raw_sql_preserves_query_error_when_close_raises_405(
    offline_backend: Backend,
) -> None:
    query_error = trino.exceptions.TrinoQueryError(
        {
            "message": "line 1:1: Table not found",
            "errorCode": 46,
            "errorName": "TABLE_NOT_FOUND",
            "errorType": "USER_ERROR",
        },
        query_id="q-test",
    )
    close_error = trino.exceptions.HttpError("error 405")

    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = query_error
    mock_cursor.close.side_effect = close_error
    mock_cursor._query = MagicMock()

    mock_con = MagicMock()
    mock_con.cursor.return_value = mock_cursor
    mock_con.transaction = None

    original_con = offline_backend.con
    try:
        offline_backend.con = mock_con
        with pytest.raises(trino.exceptions.TrinoQueryError) as exc_info:
            offline_backend.raw_sql("SELECT 1")
        assert "Table not found" in str(exc_info.value)
    finally:
        offline_backend.con = original_con
