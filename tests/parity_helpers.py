"""Strict Trino vs REST parity helpers (no post-fetch normalization)."""

from __future__ import annotations

from collections.abc import Callable

import ibis
import pandas as pd
from ibis.expr.types.rich import to_rich
from ibis_dune import Backend


def format_parity_failure(trino_df: pd.DataFrame, api_df: pd.DataFrame) -> str:
    """Return side-by-side dtypes and values for pytest failure output."""
    lines = [
        "=== dtypes (Trino) ===",
        str(trino_df.dtypes),
        "=== dtypes (REST)  ===",
        str(api_df.dtypes),
        "=== Trino DataFrame ===",
        trino_df.to_string(),
        "=== REST DataFrame  ===",
        api_df.to_string(),
    ]
    return "\n".join(lines)


def format_schema_failure(trino_schema: ibis.Schema, api_schema: ibis.Schema) -> str:
    """Return side-by-side ibis schema signatures."""
    return f"=== Trino schema ===\n{trino_schema}\n=== REST schema  ===\n{api_schema}"


def schema_signature(schema: ibis.Schema) -> dict[str, str]:
    """Return column name -> dtype string mapping for strict comparison."""
    return {name: str(dtype) for name, dtype in schema.items()}


def assert_execute_parity(
    trino_be: Backend,
    api_be: Backend,
    build: Callable[[Backend], ibis.Table],
) -> None:
    """Assert ``execute()`` returns identical DataFrames (dtypes, values, row order)."""
    trino_df = build(trino_be).execute()
    api_df = build(api_be).execute()
    try:
        pd.testing.assert_frame_equal(trino_df, api_df, check_dtype=True)
    except AssertionError as exc:
        raise AssertionError(
            f"{exc}\n\n{format_parity_failure(trino_df, api_df)}"
        ) from exc


def assert_pyarrow_parity(
    trino_be: Backend,
    api_be: Backend,
    build: Callable[[Backend], ibis.Table],
) -> None:
    """Assert ``to_pyarrow()`` returns strictly equal tables."""
    trino_t = build(trino_be).to_pyarrow()
    api_t = build(api_be).to_pyarrow()
    if trino_t.equals(api_t):
        return
    trino_pd = trino_t.to_pandas()
    api_pd = api_t.to_pandas()
    raise AssertionError(
        "PyArrow mismatch\n"
        f"Trino schema: {trino_t.schema}\n"
        f"REST schema:  {api_t.schema}\n"
        f"Trino:\n{trino_pd.to_string()}\n"
        f"REST:\n{api_pd.to_string()}"
    )


def assert_schema_parity(
    trino_be: Backend, api_be: Backend, table: str, database: str
) -> None:
    """Assert ``get_schema`` agrees on column names and dtype strings."""
    trino_schema = trino_be.get_schema(table, database=database)
    api_schema = api_be.get_schema(table, database=database)
    if schema_signature(trino_schema) == schema_signature(api_schema):
        return
    raise AssertionError(format_schema_failure(trino_schema, api_schema))


def assert_sql_infer_schema_parity(
    trino_be: Backend,
    api_be: Backend,
    inner_sql: str,
) -> None:
    """Assert ``_infer_schema_for_sql`` agrees on both backends."""
    trino_schema = trino_be._infer_schema_for_sql(inner_sql)
    api_schema = api_be._infer_schema_for_sql(inner_sql)
    if schema_signature(trino_schema) == schema_signature(api_schema):
        return
    raise AssertionError(format_schema_failure(trino_schema, api_schema))


def render_preview(
    expr: ibis.Table,
    *,
    console_width: int | float | None = 200,
    max_columns: int | None = None,
    capture_width: int | None = None,
) -> str:
    """Capture rich preview text for an ibis table expression."""
    from rich.console import Console

    rich_table = to_rich(expr, max_columns=max_columns, console_width=console_width)
    width = capture_width
    if width is None and console_width == float("inf"):
        width = 10_000
    console = Console(force_terminal=False, width=width)
    with console.capture() as capture:
        console.print(rich_table)
    return capture.get().rstrip()


def assert_preview_parity(
    trino_be: Backend,
    api_be: Backend,
    build: Callable[[Backend], ibis.Table],
    *,
    console_width: int = 200,
    max_columns: int | None = None,
) -> None:
    """Assert rich preview text is identical on Trino and REST paths."""
    trino_text = render_preview(
        build(trino_be), console_width=console_width, max_columns=max_columns
    )
    api_text = render_preview(
        build(api_be), console_width=console_width, max_columns=max_columns
    )
    if trino_text == api_text:
        return
    raise AssertionError(
        "Preview mismatch\n"
        f"=== Trino preview ===\n{trino_text}\n"
        f"=== REST preview  ===\n{api_text}"
    )


def assert_all_columns_rendered(
    expr: ibis.Table,
    *,
    console_width: int | float | None = float("inf"),
) -> None:
    """Assert every column name appears in the preview with no ``…`` column."""
    # ibis treats max_columns=0 as unlimited (None falls back to global default).
    rich_table = to_rich(expr, max_columns=0, console_width=console_width)
    assert len(rich_table.columns) == len(
        expr.columns
    ), f"expected {len(expr.columns)} columns, rich table has {len(rich_table.columns)}"
    text = render_preview(expr, console_width=console_width, max_columns=0)
    for name in expr.columns:
        assert name in text, f"column {name!r} missing from preview:\n{text}"
