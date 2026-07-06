from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from typing import Any

import trino
from dune_client.api.base import MAX_NUM_ROWS_PER_BATCH
from dune_client.client import DuneClient
from dune_client.models import ExecutionState, QueryFailedError, ResultsResponse
from requests.exceptions import RetryError

from ibis_dune.compiler import compiler as dune_compiler
from ibis_dune.exceptions import DuneQueryError, DuneResultTooLargeError
from ibis_dune.formats import is_large_decimal

log = logging.getLogger(__name__)

EXECUTION_STATUS_POLL_INITIAL_SECONDS = 1.0
EXECUTION_STATUS_POLL_MAX_SECONDS = 5.0
EXECUTION_STATUS_POLL_MULTIPLIER = 1.1
RATE_LIMIT_RETRY_SLEEP_SECONDS = 60.0
RATE_LIMIT_MAX_RETRIES = 3
_ALLOW_PARTIAL_RESULTS = "false"


class ApiExecutionMixin:
    """Trino execution with automatic fallback to Dune REST /sql/execute."""

    name = "dune"
    compiler = dune_compiler

    force_api: bool
    _use_api: bool
    dune_api_key: str
    dune_client: DuneClient
    dune_sql_performance: str
    dune_api_warning_bytes: int
    dune_api_max_bytes: int

    @property
    def uses_api(self) -> bool:
        """Return whether execution is currently routed through Dune REST."""
        return self.force_api or self._use_api

    @staticmethod
    def is_invalid_performance_tier_error(exc: BaseException) -> bool:
        """Return whether ``exc`` indicates Trino tier rejection."""
        return "Invalid performance tier" in str(exc)

    @staticmethod
    def _to_dune_query_error(exc: BaseException) -> DuneQueryError:
        """Wrap a Trino failure in a compact ``DuneQueryError``."""
        if isinstance(exc, trino.exceptions.TrinoQueryError):
            return DuneQueryError(
                message=exc.message,
                query_id=getattr(exc, "query_id", None),
                original=exc,
            )
        if isinstance(exc, trino.exceptions.HttpError):
            return DuneQueryError(message=str(exc), original=exc)
        raise TypeError(f"expected TrinoQueryError or HttpError, got {type(exc)!r}")

    @staticmethod
    def _is_null(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        try:
            import pandas as pd

            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _hex_like_to_bytes(value: Any) -> Any:
        if ApiExecutionMixin._is_null(value):
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            s = value.strip()
            if s.startswith("0x"):
                s = s[2:]
            if not s:
                return b""
            return bytes.fromhex(s)
        return value

    @staticmethod
    def _binary_for_pandas(value: Any) -> Any:
        """Match Trino pandas output: varbinary columns as ``0x`` hex strings."""
        b = ApiExecutionMixin._hex_like_to_bytes(value)
        if b is None:
            return None
        return "0x" + b.hex().lower()

    @staticmethod
    def _coerce_rest_scalar(value: Any, dtype: Any) -> Any:
        if ApiExecutionMixin._is_null(value):
            return None
        if dtype.is_binary():
            return ApiExecutionMixin._hex_like_to_bytes(value)
        if dtype.is_decimal():
            from ibis.formats.pandas import normalize_decimal

            return normalize_decimal(
                value,
                precision=dtype.precision,
                scale=dtype.scale,
                strict=False,
            )
        return value

    @staticmethod
    def _normalize_rest_column_name(name: str) -> str:
        """Normalize Dune REST column names to match ibis schema keys."""
        from ibis_dune.schema_fetch import SchemaFetchMixin

        return SchemaFetchMixin._normalize_api_column_name(name).casefold()

    @staticmethod
    def _rest_rows_to_dataframe(
        rows: list[dict[str, Any]],
        schema: Any,
        *,
        column_names: list[str] | None = None,
    ) -> Any:
        """Coerce Dune REST JSON rows to match an ibis schema (for pandas/pyarrow)."""
        import pandas as pd
        from ibis.formats.pandas import PandasData

        normalize = ApiExecutionMixin._normalize_rest_column_name
        columns = list(schema.names)

        if rows and column_names:
            key_lookup = {normalize(key): key for key in rows[0]}
            normalized_names = [normalize(name) for name in column_names]
            data = [
                {norm: row.get(key_lookup.get(norm, norm)) for norm in normalized_names}
                for row in rows
            ]
            df = pd.DataFrame(data, columns=normalized_names)
        else:
            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.rename(columns={col: normalize(col) for col in df.columns})

        if columns:
            df = df.reindex(columns=columns)

        for name, dtype in schema.items():
            if name not in df.columns:
                continue
            if dtype.is_binary():
                df[name] = df[name].map(ApiExecutionMixin._binary_for_pandas)
            elif dtype.is_decimal():
                df[name] = df[name].map(
                    partial(ApiExecutionMixin._coerce_rest_scalar, dtype=dtype)
                )

        return PandasData.convert_table(df, schema)

    @staticmethod
    def _value_for_pyarrow(value: Any, dtype: Any) -> Any:
        """Convert a pandas cell to a value compatible with ibis' PyArrow struct preview."""
        import ibis.expr.datatypes as dt
        import pandas as pd
        import pyarrow as pa
        from ibis.formats.pyarrow import PyArrowType

        if ApiExecutionMixin._is_null(value):
            return None

        if isinstance(dtype, dt.Decimal) or dtype.is_decimal():
            coerced = ApiExecutionMixin._coerce_rest_scalar(value, dtype)
            if is_large_decimal(dtype):
                return str(coerced) if coerced is not None else None
            pa_type = PyArrowType.from_ibis(dtype)
            if pa.types.is_string(pa_type):
                return str(coerced) if coerced is not None else None
            return coerced

        pa_type = PyArrowType.from_ibis(dtype)

        if pa.types.is_binary(pa_type):
            hex_string = ApiExecutionMixin._binary_for_pandas(value)
            return hex_string.encode("ascii") if hex_string is not None else None

        if pa.types.is_string(pa_type):
            return str(value)

        if dtype.is_integer():
            return int(value)

        if dtype.is_timestamp():
            ts = pd.Timestamp(value)
            if dtype.timezone is not None:
                if ts.tzinfo is None:
                    ts = ts.tz_localize(dtype.timezone)
                else:
                    ts = ts.tz_convert(dtype.timezone)
            return ts.to_pydatetime()

        if dtype.is_date():
            return pd.Timestamp(value).date()

        return value

    @staticmethod
    def _dataframe_to_batches(
        df: Any,
        schema: Any,
        chunk_size: int,
    ) -> Iterable[list[tuple[Any, ...]]]:
        names = list(schema.names)
        batch: list[tuple[Any, ...]] = []
        for i in range(len(df)):
            row = tuple(
                ApiExecutionMixin._value_for_pyarrow(df.iloc[i][name], schema[name])
                for name in names
            )
            batch.append(row)
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def reset_to_trino(self) -> None:
        """Clear tier-triggered API mode (does not override ``force_api``)."""
        self._use_api = False

    def _call_dune_api(self, fn: Callable[[], Any]) -> Any:
        """Run a Dune REST call; on 429 RetryError, sleep 60s and retry up to 3 times."""
        for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
            try:
                return fn()
            except RetryError as exc:
                if attempt >= RATE_LIMIT_MAX_RETRIES:
                    raise
                msg = (
                    f"Dune API rate limited ({exc}); sleeping "
                    f"{RATE_LIMIT_RETRY_SLEEP_SECONDS:.0f}s before retry "
                    f"({attempt + 1}/{RATE_LIMIT_MAX_RETRIES})"
                )
                log.warning(msg)
                time.sleep(RATE_LIMIT_RETRY_SLEEP_SECONDS)

    def _wait_for_execution(self, job_id: str):
        status = self._call_dune_api(
            lambda: self.dune_client.get_execution_status(job_id)
        )
        poll_interval = EXECUTION_STATUS_POLL_INITIAL_SECONDS

        while status.state not in ExecutionState.terminal_states():
            log.debug(
                "waiting for Dune SQL execution %s: %s (sleep %.2fs)",
                job_id,
                status.state,
                poll_interval,
            )
            time.sleep(poll_interval)
            status = self._call_dune_api(
                lambda: self.dune_client.get_execution_status(job_id)
            )
            poll_interval = min(
                poll_interval * EXECUTION_STATUS_POLL_MULTIPLIER,
                EXECUTION_STATUS_POLL_MAX_SECONDS,
            )

        return status

    def _execute_sql_via_api(self, sql: str) -> tuple[list[dict[str, Any]], list[str]]:
        first = self._execute_sql_first_page(sql)
        if first.result is None:
            raise RuntimeError("Dune SQL execution completed without a result payload")

        total_bytes = first.result.metadata.total_result_set_bytes
        self._enforce_result_size_limits(total_bytes)

        column_names = list(first.result.metadata.column_names)
        rows = list(first.result.rows)
        rows.extend(self._fetch_remaining_pages(first))
        return rows, column_names

    def _execute_expr_via_api(
        self,
        expr: Any,
        *,
        params: Mapping | None = None,
        limit: int | str | None = None,
        **kwargs: Any,
    ) -> Any:
        self._run_pre_execute_hooks(expr)
        table = expr.as_table()
        sql = self.compile(table, params=params, limit=limit, **kwargs)
        schema = table.schema()
        rows, column_names = self._execute_sql_via_api(sql)
        return self._rest_rows_to_dataframe(rows, schema, column_names=column_names)

    def execute(  # type: ignore[no-untyped-def]
        self,
        expr,
        /,
        *,
        params: Mapping | None = None,
        limit: int | str | None = None,
        **kwargs: Any,
    ):
        """Execute an ibis expression via Trino or Dune REST and return pandas output."""
        if self.uses_api:
            self._log_api_execution()
            df = self._execute_expr_via_api(expr, params=params, limit=limit, **kwargs)
            return expr.__pandas_result__(df)

        try:
            return super().execute(expr, params=params, limit=limit, **kwargs)  # type: ignore[misc]
        except trino.exceptions.TrinoUserError as e:
            if self.is_invalid_performance_tier_error(e):
                self._log_trino_tier_fallback(e)
                self._use_api = True
                df = self._execute_expr_via_api(
                    expr, params=params, limit=limit, **kwargs
                )
                return expr.__pandas_result__(df)
            raise self._to_dune_query_error(e) from None
        except trino.exceptions.TrinoQueryError as e:
            raise self._to_dune_query_error(e) from None
        except trino.exceptions.HttpError as e:
            raise self._to_dune_query_error(e) from None

    def _cursor_batches(  # type: ignore[no-untyped-def]
        self,
        expr,
        params: Mapping | None = None,
        limit: int | str | None = None,
        chunk_size: int = 1 << 20,
    ) -> Iterable[list]:
        """Yield cursor batches via Trino or REST, honoring ``params`` and ``limit``."""
        if self.uses_api:
            self._log_api_execution()
            df = self._execute_expr_via_api(expr, params=params, limit=limit)
            yield from self._dataframe_to_batches(
                df, expr.as_table().schema(), chunk_size
            )
            return

        try:
            yield from super()._cursor_batches(  # type: ignore[misc]
                expr, params=params, limit=limit, chunk_size=chunk_size
            )
        except trino.exceptions.TrinoUserError as e:
            if self.is_invalid_performance_tier_error(e):
                self._log_trino_tier_fallback(e)
                self._use_api = True
                df = self._execute_expr_via_api(expr, params=params, limit=limit)
                yield from self._dataframe_to_batches(
                    df, expr.as_table().schema(), chunk_size
                )
                return
            raise self._to_dune_query_error(e) from None
        except trino.exceptions.TrinoQueryError as e:
            raise self._to_dune_query_error(e) from None
        except trino.exceptions.HttpError as e:
            raise self._to_dune_query_error(e) from None

    def _enforce_result_size_limits(self, total_bytes: int) -> None:
        if total_bytes > self.dune_api_max_bytes:
            raise DuneResultTooLargeError(
                message="Refusing to fetch full result set",
                total_bytes=total_bytes,
                max_bytes=self.dune_api_max_bytes,
            )
        if total_bytes > self.dune_api_warning_bytes:
            log.warning(
                "Dune REST result is %s bytes (dune_api_warning_bytes=%s); "
                "fetching full result set",
                total_bytes,
                self.dune_api_warning_bytes,
            )

    def _execute_sql_first_page(self, sql: str) -> ResultsResponse:
        job_id = self._call_dune_api(
            lambda: self.dune_client.execute_sql(
                query_sql=sql, performance=self.dune_sql_performance
            )
        ).execution_id

        status = self._wait_for_execution(job_id)

        if status.state == ExecutionState.FAILED:
            if status.error:
                raise self._to_dune_query_error_from_rest(
                    QueryFailedError(status.error.message)
                ) from None
            raise self._to_dune_query_error_from_rest(
                QueryFailedError("Query execution failed")
            ) from None

        return self._call_dune_api(
            lambda: self.dune_client.get_execution_results(
                job_id,
                limit=MAX_NUM_ROWS_PER_BATCH,
                allow_partial_results=_ALLOW_PARTIAL_RESULTS,
            )
        )

    def _fetch_remaining_pages(self, page: ResultsResponse) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        next_uri = page.next_uri
        while next_uri is not None:
            batch = self._call_dune_api(
                lambda uri=next_uri: self.dune_client._get_execution_results_by_url(  # noqa: SLF001
                    url=uri,
                    params={"allow_partial_results": _ALLOW_PARTIAL_RESULTS},
                )
            )
            if batch.result is not None:
                rows.extend(batch.result.rows)
            next_uri = batch.next_uri
        return rows

    @staticmethod
    def _to_dune_query_error_from_rest(exc: QueryFailedError) -> DuneQueryError:
        """Wrap a Dune REST ``QueryFailedError`` as a ``DuneQueryError``."""
        return DuneQueryError(message=str(exc), original=exc)

    def _log_trino_tier_fallback(self, exc: trino.exceptions.TrinoUserError) -> None:
        log.warning(
            "Trino query failed (%s); switching to Dune REST /sql/execute "
            "(performance=%s): %s",
            type(exc).__name__,
            self.dune_sql_performance,
            exc,
        )

    def _log_api_execution(self) -> None:
        if self.force_api and not self._use_api:
            log.debug(
                "Executing via Dune REST /sql/execute (force_api=True, performance=%s)",
                self.dune_sql_performance,
            )
        elif self._use_api:
            log.debug(
                "Executing via Dune REST /sql/execute (performance=%s)",
                self.dune_sql_performance,
            )
