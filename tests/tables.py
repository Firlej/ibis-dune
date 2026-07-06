"""Credit-safe Dune table builders for integration and parity tests.

Only two scanned tables are referenced here:

- ``iq_protocol_polygon.enterprise_evt_rented`` (~6-7k static rows) — uint256 + binary.
- ``ethereum.logs`` filtered to ``block_date = '2015-08-08'`` — binary ``data`` incl. empty ``0x``.

Plus a zero-scan ``scalar_constants`` ``sql()`` probe. Always filter/limit before execute.
"""

from __future__ import annotations

from collections.abc import Callable

import ibis
from ibis import _
from ibis_dune import Backend
from ibis_dune.ops import hex_literal, raw_predicate, raw_scalar

# --- iq_protocol_polygon.enterprise_evt_rented (~6-7k rows, static) ---
RENTED_DB = "iq_protocol_polygon"
RENTED_TABLE = "enterprise_evt_rented"
RENTED_CONTRACT = "0xbf9f6b1d910aa207daa400931430ef110570f8ff"
RENTED_TX_HASH = "0x06c4bf3d702b2adbadb52230a2d1c507da55b2ef07b285fe3a4d55f8daf475be"
RENTED_RENTALTOKENID = (
    115597092877761069019903437234573841225780679087707680554709867281103459621204
)

# --- ethereum.logs, one early day (binary ``data``, incl. empty 0x) ---
LOGS_DB = "ethereum"
LOGS_TABLE = "logs"
LOGS_DATE = "2015-08-08"


def rented(backend: Backend) -> ibis.Table:
    """Return the full ``enterprise_evt_rented`` table expression."""
    return backend.table(RENTED_TABLE, database=RENTED_DB)


def rented_one_row(backend: Backend) -> ibis.Table:
    """Return one deterministic row (uint256 + binary columns)."""
    return (
        rented(backend)
        .filter(
            ibis.and_(
                _.contract_address == hex_literal(RENTED_CONTRACT),
                _.evt_tx_hash == hex_literal(RENTED_TX_HASH),
            )
        )
        .order_by(_.evt_block_number, _.evt_index)
    )


def rented_raw_predicate(backend: Backend) -> ibis.Table:
    """Exercise ``raw_predicate`` on a filtered, ordered slice of ``rented``."""
    return (
        rented(backend)
        .filter(raw_predicate(f"contract_address = {RENTED_CONTRACT}"))
        .order_by(_.evt_block_number, _.evt_index)
        .limit(2)
    )


def rented_raw_scalar(backend: Backend) -> ibis.Table:
    """Exercise ``raw_scalar`` on the deterministic single row."""
    return (
        rented_one_row(backend)
        .select(_.evt_block_number, probe=raw_scalar("CAST(42 AS BIGINT)", "int64"))
        .order_by(_.evt_block_number)
    )


def rented_sample(backend: Backend) -> ibis.Table:
    """Small ordered slice for API byte-limit integration tests."""
    return (
        rented(backend)
        .order_by(_.evt_block_number, _.evt_index)
        .select("rentaltokenid", "contract_address")
        .limit(5)
    )


def logs_early_day(backend: Backend) -> ibis.Table:
    """Partition-pruned early-day ``ethereum.logs`` slice."""
    return (
        backend.table(LOGS_TABLE, database=LOGS_DB)
        .filter(_.block_date == ibis.literal(LOGS_DATE, type="date"))
        .order_by(_.block_number, _.index)
    )


def logs_data_sample(backend: Backend) -> ibis.Table:
    """Ordered binary ``data`` sample including empty ``0x`` values."""
    return (
        logs_early_day(backend)
        .select("block_number", "index", "data")
        .order_by(_.block_number, _.index)
        .limit(6)
    )


def scalar_constants(backend: Backend) -> ibis.Table:
    """Zero-scan scalar ``sql()`` for coercion and schema-inference probes."""
    return backend.sql(
        "SELECT CAST(42 AS BIGINT) AS n, CAST(1.5 AS DOUBLE) AS f, "
        "TIMESTAMP '2024-01-01 00:00:00' AS ts, 'x' AS s "
        "ORDER BY n"
    )


PARITY_BUILDERS: dict[str, Callable[[Backend], ibis.Table]] = {
    "rented_one_row": rented_one_row,
    "logs_data_sample": logs_data_sample,
    "scalar_constants": scalar_constants,
}
