# ibis-dune

<p align="center">
  <a href="https://github.com/Firlej/ibis-dune/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://github.com/Firlej/ibis-dune/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/ibis-dune/"><img src="https://img.shields.io/pypi/v/ibis-dune.svg?style=flat-square&logo=pypi&logoColor=white&label=pypi" alt="PyPI version"></a>
  <a href="https://pypi.org/project/ibis-dune/"><img src="https://img.shields.io/pypi/pyversions/ibis-dune.svg?style=flat-square&logo=python&logoColor=white" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License: Apache 2.0"></a>
  <a href="https://pepy.tech/projects/ibis-dune"><img src="https://static.pepy.tech/personalized-badge/ibis-dune?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads" alt="PyPI downloads"></a>
  <a href="https://github.com/Firlej/ibis-dune/stargazers"><img src="https://img.shields.io/github/stars/Firlej/ibis-dune?style=social" alt="GitHub stars"></a>
</p>

Ibis backend for [Dune Analytics](https://dune.com).

## Overview

**ibis-dune** lets you query Dune with [Ibis](https://ibis-project.org/) table expressions: build filters, joins, and aggregates in Python, compile them to Dune SQL, and execute on Trino (`trino.api.dune.com`).

A **paid Dune API plan with Trino access** is required. Free-tier keys can no longer run queries; the backend does not fall back to REST `/sql/execute`.

The backend handles Dune-specific concerns that plain Trino backends do not:

- **Schema discovery** — `get_schema()` uses `information_schema`, then a Trino `LIMIT 0` probe. Schema-less `sql()` infers types with `LIMIT 0` only.
- **uint256** — Dune `uint256` is `decimal(78, 0)` in the compiler, PyArrow, and rich preview.
- **varbinary** — `get_schema()` reports `contract_address` as binary via `information_schema`. Schema-less `sql()` follows the Trino cursor type and reports it as string (varchar).
- **Dune SQL helpers** — `hex_literal`, `raw_predicate`, and `raw_scalar` for fragments Ibis cannot express natively
- **Typed errors** — `DuneQueryError` at the execution boundary, including a paid-plan hint when Trino rejects the performance tier

> Install **`ibis-framework`** from PyPI, not the legacy `ibis` package. Both import as `ibis` and cannot coexist.

## Install

Requires **Python 3.11+**.

```bash
pip install ibis-dune
```

This pulls in `ibis-framework[trino]` (12.x) and `sqlglot` (>=26.4).

You need a [Dune API key](https://dune.com/docs/api/introduction) on a plan that includes Trino.

## Usage

```python
import ibis

con = ibis.dune.connect(dune_api_key="YOUR_DUNE_API_KEY")
```

Or import the backend directly:

```python
from ibis_dune import Backend

con = Backend().connect(dune_api_key="YOUR_DUNE_API_KEY")
```

## Connection options

`Backend().connect()` / `ibis.dune.connect()` accept:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `dune_api_key` | (required) | Dune API key with Trino access |
| `**kwargs` | | Forwarded to the Ibis Trino backend |

## Example

```python
import ibis

con = ibis.dune.connect(dune_api_key="YOUR_DUNE_API_KEY")

t = con.sql("SELECT CAST(42 AS BIGINT) AS n")
print(t.execute())
```

When querying Dune tables directly, always keep scans bounded — filter partitions and add `.limit()`:

```python
from ibis import _

t = (
    con.table("logs", database="ethereum")
    .filter(_.block_date == ibis.literal("2015-08-08", type="date"))
    .select("block_number", "index", "data")
    .limit(5)
)
print(t.execute())
```

## Examples

[examples/dune_types.ipynb](examples/dune_types.ipynb) is an executed notebook: uint256 and binary columns on one row of `iq_protocol_polygon.enterprise_evt_rented`, plus `hex_literal`, `raw_predicate`, and `raw_scalar`. Export `DUNE_API_KEY` before re-running it.

## Dune SQL helpers

Dune-specific SQL fragments compile through the backend compiler:

```python
from ibis import _
from ibis_dune.ops import hex_literal, raw_predicate, raw_scalar

t = con.table("enterprise_evt_rented", database="iq_protocol_polygon")
t = t.filter(_.contract_address == hex_literal("0xbf9f6b1d910aa207daa400931430ef110570f8ff"))
t = t.filter(raw_predicate("evt_block_number > 1000"))
t = t.select(probe=raw_scalar("CAST(42 AS BIGINT)", "int64")).limit(5)
```

- `hex_literal` — validated hex string literal (Dune `HEX` syntax)
- `raw_predicate` — verbatim Trino SQL boolean filter
- `raw_scalar` — verbatim Trino SQL expression with an explicit ibis dtype

## Errors

- `DuneQueryError` — wraps Trino query failures at the execution boundary. Invalid performance tier errors include a paid-plan hint.

## Releases

Release notes live on [GitHub Releases](https://github.com/Firlej/ibis-dune/releases). Each version tag has a curated release page with fixed/improved/features sections.

When cutting a new release, add `.github/release-notes/vX.Y.Z.md` with the notes body, bump the version, tag, and push — the release workflow publishes the GitHub Release and attaches build artifacts.

## Development

```bash
git clone https://github.com/Firlej/ibis-dune.git
cd ibis-dune
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

Offline tests (CI gate, no API key):

```bash
pytest -m "not integration" -q
```

For integration tests against live Dune, copy `tests/.env.example` to `tests/.env` and set `DUNE_API_KEY` (paid Trino) and optionally `DUNE_API_KEY_FREE` (denied-path error tests).

To build and validate a release artifact locally:

```bash
python -m build
twine check dist/*
```

See [UPSTREAM.md](UPSTREAM.md) for upstream merge notes and publishing workflow.

## License

Apache-2.0 — see [LICENSE](LICENSE).
