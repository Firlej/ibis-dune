from __future__ import annotations

import ibis
import ibis.expr.operations as ops
import ibis.expr.schema as sch


class SqlMethodMixin:
    """``sql()`` with automatic schema inference when ``schema`` is omitted."""

    def _get_schema_using_query(self, query: str) -> sch.Schema:
        inner = self._strip_trailing_semicolon(query)
        return self._infer_schema_for_sql(inner)

    def sql(  # type: ignore[no-untyped-def]
        self,
        query: str,
        /,
        *,
        schema=None,
        dialect=None,
    ):
        """Return a table expression for raw SQL, inferring schema when ``schema`` is omitted."""
        if schema is not None:
            return super().sql(query, schema=schema, dialect=dialect)  # type: ignore[misc]

        query = self._transpile_sql(query, dialect=dialect)
        inner = self._strip_trailing_semicolon(query)
        # Subquery alias lets Dune/Trino infer column names from the inner SELECT.
        wrapped = f"SELECT * FROM (\n{inner}\n) AS _ibis_dune_raw_sql"
        inferred = self._infer_schema_for_sql(inner)
        return ops.SQLQueryResult(wrapped, ibis.schema(inferred), self).to_expr()
