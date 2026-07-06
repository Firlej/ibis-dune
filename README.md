# ibis-dune

Ibis backend for [Dune Analytics](https://dune.com).

## Overview

**ibis-dune** lets you query Dune with [Ibis](https://ibis-project.org/) table expressions: build filters, joins, and aggregates in Python, compile them to Dune SQL, and execute on Trino (`trino.api.dune.com`). When your API plan cannot use Trino, the backend automatically falls back to Dune REST `/sql/execute` and keeps results consistent across both paths.

The backend handles Dune-specific concerns that plain Trino backends do not:

- **Schema discovery** — `get_schema()` and schema-less `sql()` infer column types without hand-written schemas
- **uint256 and varbinary** — large integers and binary columns round-trip correctly in pandas, PyArrow, and rich previews
- **Dune SQL helpers** — `hex_literal`, `raw_predicate`, and `raw_scalar` for fragments Ibis cannot express natively
- **Typed errors** — `DuneQueryError` and `DuneResultTooLargeError` at the execution boundary

> Install **`ibis-framework`** from PyPI, not the legacy `ibis` package. Both import as `ibis` and cannot coexist.

## Install

Requires **Python 3.11+**.

```bash
pip install ibis-dune
```

This pulls in `ibis-framework[trino]` (12.x) and `dune-client` (>=1.10).

You need a [Dune API key](https://dune.com/docs/api/introduction) for live queries.

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

By default queries run on Trino. If Trino rejects the performance tier, the backend switches to REST for that session. Call `con.reset_to_trino()` to try Trino again. Pass `force_api=True` to start on REST.

## Connection options

`Backend().connect()` / `ibis.dune.connect()` accept:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `dune_api_key` | (required) | Dune API key |
| `force_api` | `False` | Start on REST instead of Trino |
| `dune_sql_performance` | `"medium"` | REST `/sql/execute` performance tier |
| `dune_api_warning_bytes` | `1 GiB` | Log a warning when REST result exceeds this size |
| `dune_api_max_bytes` | `4 GiB` | Refuse to fetch REST results larger than this |

After connect, `con.uses_api` is `True` when execution is routed through REST (either `force_api=True` or tier-triggered fallback). `con.reset_to_trino()` clears tier-triggered fallback but does not override `force_api`.

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

- `DuneQueryError` — wraps Trino and REST query failures at the execution boundary
- `DuneResultTooLargeError` — raised when a REST result exceeds `dune_api_max_bytes`

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
pytest -m "not integration and not trino and not parity_mock" -q
```

For integration tests against live Dune, copy `tests/.env.example` to `tests/.env` and set `DUNE_API_KEY`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for test tiers, fixture refresh, and local workflow details.

To build and validate a release artifact locally:

```bash
python -m build
twine check dist/*
```

See [UPSTREAM.md](UPSTREAM.md) for upstream merge notes and publishing workflow.

## License

Apache-2.0 — see [LICENSE](LICENSE).
