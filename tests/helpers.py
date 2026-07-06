"""Build ibis table expressions without schema fetch (offline compile tests)."""

from __future__ import annotations

import ibis
from ibis.expr.operations import DatabaseTable, Namespace
from ibis_dune import Backend


def bound_table(
    backend: Backend,
    name: str,
    database: str,
    schema: ibis.Schema | None = None,
) -> ibis.Table:
    """Return a table expression bound to ``backend`` with an explicit schema."""
    if schema is None:
        schema = ibis.schema({"contract_address": "string", "evt_tx_hash": "string"})
    return DatabaseTable(
        name=name,
        schema=schema,
        source=backend,
        namespace=Namespace(catalog=None, database=database),
    ).to_expr()
