# Changelog

All notable changes to this project are documented here.

## 0.1.0 — 2026-07-06

First public release of **ibis-dune**: an Ibis backend for querying [Dune Analytics](https://dune.com) with Python table expressions.

### Features

#### Ibis integration

- Register as a standard Ibis backend (`dune` entry point): `ibis.dune.connect(dune_api_key=...)` or `Backend().connect(...)`
- Build and execute Ibis table expressions against Dune datasets — `table()`, filters, projections, joins, aggregates, and `sql()` compile to Dune SQL via the sqlglot `Dune` dialect
- `sql(query)` infers column types automatically when `schema` is omitted

#### Execution (Trino + REST)

- Primary execution path: Trino at `trino.api.dune.com`
- Automatic fallback to Dune REST `/sql/execute` when Trino rejects the API performance tier; session stays on REST until `reset_to_trino()` is called
- `force_api=True` to start on REST; `uses_api` reports the active transport
- Configurable REST SQL performance tier (`dune_sql_performance`) and result size limits (`dune_api_warning_bytes`, `dune_api_max_bytes`)
- REST path honors `limit` and `params` the same way as Trino; paginates large REST results and retries on rate limits

#### Trino / REST result parity

- `execute()`, `to_pyarrow()`, and rich table previews return equivalent dtypes, values, and row order on Trino and REST paths
- REST JSON rows are coerced to match Trino output: decimals normalized, varbinary as `0x`-prefixed hex strings, Dune REST column names normalized to ibis schema keys

#### Schema discovery

- `get_schema(table, database=...)` via `information_schema` with LIMIT 0 fallback when metadata is empty
- Hybrid type inference: prefers Dune REST `column_types` when Trino cursor metadata is lossy (e.g. `varbinary` reported as `varchar`)
- Missing table, schema, or catalog → `TableNotFound`; other backend failures → `DuneQueryError`

#### Dune-specific types and SQL helpers

- `uint256` columns map to `Decimal(78, 0)` in the Ibis type system (`DuneType` / `DuneCompiler`)
- `hex_literal(hex)` — validated hex literal compiled to Dune `HEX` syntax
- `raw_predicate(sql)` — embed verbatim Trino SQL in filters
- `raw_scalar(sql, dtype)` — embed verbatim Trino SQL in projections with an explicit Ibis dtype

#### Display and large integers

- `install_uint256_support()` and `install_rich_formatting()` applied automatically on connect (also callable directly)
- Large decimals (including uint256) use PyArrow string surrogates where needed; rich previews label uint256 and render binary columns as hex

#### Errors and robustness

- `DuneQueryError` — compact wrapper for Trino and REST query failures (including REST `QueryFailedError`)
- `DuneResultTooLargeError` — raised when a REST result exceeds `dune_api_max_bytes`
- Trino cursor cleanup preserves the original query error when close raises HTTP 405

#### Packaging

- Typed package (`py.typed`); supports Python 3.11, 3.12, and 3.13
- Depends on `ibis-framework[trino]` 12.x and `dune-client` >= 1.10.0

### Requirements

- Python **3.11+**
- `ibis-framework[trino]` **>=12, <13**
- `dune-client` **>=1.10.0**
