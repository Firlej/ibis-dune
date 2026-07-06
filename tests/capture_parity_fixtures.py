"""Capture Trino goldens and raw REST payloads for offline parity replay."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import ibis
import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
from ibis_dune import Backend

from tests.tables import LOGS_DB, LOGS_TABLE, PARITY_BUILDERS, RENTED_DB, RENTED_TABLE

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def trino_execute_fixture_path(name: str) -> Path:
    """Return the path for a captured Trino execute golden."""
    return FIXTURES_DIR / f"{name}_trino_execute.pkl"


def trino_pyarrow_fixture_path(name: str) -> Path:
    """Return the path for a captured Trino PyArrow golden."""
    return FIXTURES_DIR / f"{name}_trino_pyarrow.arrow"


def rest_raw_fixture_path(name: str) -> Path:
    """Return the path for captured raw REST rows + metadata."""
    return FIXTURES_DIR / f"{name}_rest_raw.json"


def schema_fixture_path(name: str) -> Path:
    """Return the path for a captured builder schema fixture."""
    return FIXTURES_DIR / f"{name}_schema.json"


def _schema_to_payload(schema: ibis.Schema) -> dict[str, str]:
    """Serialize an ibis schema for JSON fixture storage."""
    return {name: str(dtype) for name, dtype in schema.items()}


def _payload_to_schema(payload: dict[str, str]) -> ibis.Schema:
    """Deserialize a schema fixture."""
    return ibis.schema(payload)


def load_schema_fixture(name: str) -> ibis.Schema:
    """Load a captured ibis schema fixture."""
    return _payload_to_schema(json.loads(schema_fixture_path(name).read_text()))


def load_trino_execute_fixture(name: str) -> pd.DataFrame:
    """Load a Trino execute golden DataFrame."""
    with trino_execute_fixture_path(name).open("rb") as handle:
        return pickle.load(handle)


def load_trino_pyarrow_fixture(name: str) -> pa.Table:
    """Load a Trino PyArrow golden table."""
    with trino_pyarrow_fixture_path(name).open("rb") as handle:
        with ipc.open_file(handle) as reader:
            return reader.read_all()


def load_rest_raw_fixture(name: str) -> dict:
    """Load captured raw REST rows and metadata."""
    return json.loads(rest_raw_fixture_path(name).read_text())


def capture_all(*, dune_api_key: str) -> None:
    """Capture Trino goldens and raw REST payloads for every parity builder."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    trino_be = Backend().connect(dune_api_key=dune_api_key)
    api_be = Backend().connect(dune_api_key=dune_api_key, force_api=True)

    for name, build in PARITY_BUILDERS.items():
        trino_expr = build(trino_be)
        api_expr = build(api_be)

        trino_df = trino_expr.execute()
        with trino_execute_fixture_path(name).open("wb") as handle:
            pickle.dump(trino_df, handle)

        trino_arrow = trino_expr.to_pyarrow()
        with trino_pyarrow_fixture_path(name).open("wb") as handle:
            with ipc.new_file(handle, trino_arrow.schema) as writer:
                writer.write_table(trino_arrow)

        sql = api_be.compile(api_expr.as_table())
        first = api_be._execute_sql_first_page(sql)
        if first.result is None:
            raise RuntimeError(f"REST capture returned no result for {name}")
        rest_raw = {
            "column_names": list(first.result.metadata.column_names),
            "column_types": list(first.result.metadata.column_types),
            "rows": list(first.result.rows) + api_be._fetch_remaining_pages(first),
        }
        rest_raw_fixture_path(name).write_text(json.dumps(rest_raw, indent=2) + "\n")
        schema_fixture_path(name).write_text(
            json.dumps(_schema_to_payload(trino_expr.schema()), indent=2) + "\n"
        )

        for stale in (
            FIXTURES_DIR / f"{name}_trino.json",
            FIXTURES_DIR / f"{name}_api.json",
        ):
            if stale.exists():
                stale.unlink()

    for table_key, table_name, database in (
        ("rented_table", RENTED_TABLE, RENTED_DB),
        ("logs_table", LOGS_TABLE, LOGS_DB),
    ):
        schema = trino_be.get_schema(table_name, database=database)
        schema_fixture_path(table_key).write_text(
            json.dumps(_schema_to_payload(schema), indent=2) + "\n"
        )


if __name__ == "__main__":
    import os

    key = os.environ.get("DUNE_API_KEY")
    if not key:
        raise SystemExit("DUNE_API_KEY required to capture parity fixtures")
    capture_all(dune_api_key=key)
