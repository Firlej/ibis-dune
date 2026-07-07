from __future__ import annotations

import re

import ibis
import trino
from ibis import _
from ibis.common.exceptions import TableNotFound

from ibis_dune.exceptions import DuneQueryError

INFORMATION_SCHEMA_COLUMNS_SCHEMA = ibis.schema(
    {
        "table_catalog": "string",
        "table_schema": "string",
        "table_name": "string",
        "column_name": "string",
        "ordinal_position": "int64",
        "is_nullable": "string",
        "data_type": "string",
    }
)

_NOT_FOUND_TRINO_ERROR_NAMES = frozenset(
    {"TABLE_NOT_FOUND", "SCHEMA_NOT_FOUND", "CATALOG_NOT_FOUND"}
)
_NOT_FOUND_MESSAGE_RE = re.compile(
    r"\b(?:table|schema|catalog)\b[^\n]*does not exist",
    re.IGNORECASE,
)


class SchemaFetchMixin:
    """Schema discovery via information_schema, LIMIT 0 probes, and REST type hints."""

    @staticmethod
    def _normalize_api_column_name(name: str) -> str:
        """Strip SQL double-quotes Dune REST embeds in some ``column_names`` values."""
        if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
            return name[1:-1]
        return name

    @classmethod
    def _normalize_schema(cls, schema: ibis.Schema) -> ibis.Schema:
        if all(cls._normalize_api_column_name(n) == n for n in schema.names):
            return schema
        return ibis.Schema(
            {
                cls._normalize_api_column_name(name): dtype
                for name, dtype in schema.items()
            }
        )

    @staticmethod
    def _strip_trailing_semicolon(sql: str) -> str:
        s = sql.strip()
        s = re.sub(r";\s*$", "", s)
        return s.strip()

    @staticmethod
    def _append_limit0(sql: str) -> str:
        return f"{SchemaFetchMixin._strip_trailing_semicolon(sql)}\nLIMIT 0"

    def _schema_from_cursor_description(self, description: list) -> ibis.Schema:
        type_mapper = self.compiler.type_mapper
        return ibis.Schema(
            {
                col.name: type_mapper.from_string(col.type_code).copy(nullable=True)
                for col in description
            }
        )

    @staticmethod
    def _qualified_table_sql(
        table_name: str,
        *,
        catalog: str | None,
        database: str | None,
    ) -> str:
        if catalog is not None and database is not None:
            return f'"{catalog}"."{database}"."{table_name}"'
        if database is not None:
            return f'"{database}"."{table_name}"'
        return f'"{table_name}"'

    def get_information_schema_columns_expr(
        self,
        table_name: str,
        database: str,
    ) -> ibis.Table:
        """Return an expression for information_schema column metadata."""

        from ibis.expr.operations import (
            DatabaseTable,
            Namespace,
        )

        return (
            DatabaseTable(
                name="columns",
                schema=INFORMATION_SCHEMA_COLUMNS_SCHEMA,
                source=self,
                namespace=Namespace(catalog=None, database="information_schema"),
            )
            .to_expr()
            .filter(
                _.table_name == table_name,
                _.table_schema == database,
            )
            .order_by("ordinal_position")
            .select("column_name", "data_type")
        )

    def get_information_schema_columns_df(
        self,
        table_name: str,
        database: str,
    ):
        """Return information_schema column rows for ``(table_name, database)`` as a DataFrame."""
        return self.get_information_schema_columns_expr(
            table_name, database
        ).to_pandas()

    def schema_from_information_schema_columns_df(self, columns_df) -> ibis.Schema:
        """Build an ibis schema from information_schema ``columns`` rows."""
        if columns_df.empty:
            return ibis.schema({})

        type_mapper = self.compiler.type_mapper
        return ibis.schema(
            {
                name: type_mapper.from_string(typ)
                for name, typ in zip(
                    columns_df["column_name"],
                    columns_df["data_type"],
                    strict=True,
                )
            }
        )

    def _schema_from_information_schema(
        self,
        table_name: str,
        *,
        catalog: str | None = None,
        database: str | None = None,
    ) -> ibis.Schema:
        if database is None:
            return ibis.schema({})

        columns_df = self.get_information_schema_columns_df(table_name, database)
        return self.schema_from_information_schema_columns_df(columns_df)

    def information_schema_columns_sql(
        self,
        table_name: str,
        database: str,
    ) -> str:
        """Return compiled SQL for information_schema column metadata."""
        return self.get_information_schema_columns_expr(table_name, database).compile()

    def _prefer_api_column_types(
        self, probe_sql: str, trino_schema: ibis.Schema
    ) -> ibis.Schema:
        """Use Dune REST column_types when Trino cursor metadata is lossy (e.g. varchar for varbinary)."""
        try:
            api_schema = self._normalize_schema(self._schema_from_api_limit0(probe_sql))
        except Exception:
            return trino_schema
        if list(api_schema.names) != list(trino_schema.names):
            return trino_schema
        return api_schema

    @classmethod
    def _is_not_found_error(cls, exc: BaseException) -> bool:
        """Return whether ``exc`` indicates a missing table, schema, or catalog."""
        if getattr(exc, "error_name", None) in _NOT_FOUND_TRINO_ERROR_NAMES:
            return True
        message = getattr(exc, "message", None) or str(exc)
        return bool(_NOT_FOUND_MESSAGE_RE.search(message))

    def _schema_from_trino_limit0(self, qualified_table_sql: str) -> ibis.Schema:
        probe = f"SELECT * FROM {qualified_table_sql} LIMIT 0"
        try:
            with self.begin() as cur:
                cur.execute(probe)
                desc = cur.description
        except trino.exceptions.TrinoUserError as exc:
            if self._flip_to_api_on_tier_error(exc):
                return self._schema_from_api_limit0(
                    f"SELECT * FROM {qualified_table_sql}"
                )
            raise self._dune_query_error_from_exc(exc) from None
        except (trino.exceptions.TrinoQueryError, trino.exceptions.HttpError) as exc:
            raise self._dune_query_error_from_exc(exc) from None

        if not desc:
            raise ValueError(
                "Dune Trino returned no column metadata for schema inference "
                f"(LIMIT 0 probe). Preview: {qualified_table_sql[:500]!r}"
            )

        trino_schema = self._schema_from_cursor_description(desc)
        return self._prefer_api_column_types(
            f"SELECT * FROM {qualified_table_sql}", trino_schema
        )

    def _schema_from_api_limit0(self, sql: str) -> ibis.Schema:
        first = self._execute_sql_first_page(self._append_limit0(sql))
        if first.result is None:
            raise ValueError(
                "Dune REST returned no result for schema inference "
                f"(LIMIT 0 probe). Preview: {sql[:500]!r}"
            )

        meta = first.result.metadata
        type_mapper = self.compiler.type_mapper
        pairs = zip(meta.column_names, meta.column_types, strict=True)
        return ibis.Schema(
            {
                name: type_mapper.from_string(typ).copy(nullable=True)
                for name, typ in pairs
            }
        )

    def _infer_schema_for_sql(self, inner_sql: str) -> ibis.Schema:
        inner = self._strip_trailing_semicolon(inner_sql)
        if self.uses_api:
            schema = self._schema_from_api_limit0(inner)
        else:
            try:
                with self.begin() as cur:
                    cur.execute(self._append_limit0(inner))
                    desc = cur.description
            except trino.exceptions.TrinoUserError as exc:
                if self._flip_to_api_on_tier_error(exc):
                    schema = self._schema_from_api_limit0(inner)
                else:
                    raise self._dune_query_error_from_exc(exc) from None
            except (
                trino.exceptions.TrinoQueryError,
                trino.exceptions.HttpError,
            ) as exc:
                raise self._dune_query_error_from_exc(exc) from None
            else:
                if not desc:
                    raise ValueError(
                        "Dune Trino returned no column metadata for SQL schema inference "
                        f"(LIMIT 0 probe). Preview: {inner[:500]!r}"
                    )
                trino_schema = self._schema_from_cursor_description(desc)
                schema = self._prefer_api_column_types(inner, trino_schema)
        return self._normalize_schema(schema)

    def get_schema(
        self,
        table_name: str,
        *,
        catalog: str | None = None,
        database: str | None = None,
    ) -> ibis.Schema:
        """Return table schema, raising ``TableNotFound`` for missing objects.

        Uses information_schema when available, then falls back to LIMIT 0 probes.
        Missing table/schema/catalog errors are normalized to ``TableNotFound`` on
        both Trino and REST paths. Other backend errors surface as
        ``DuneQueryError``.
        """
        if table_name == "columns" and database == "information_schema":
            return INFORMATION_SCHEMA_COLUMNS_SCHEMA

        schema = self._schema_from_information_schema(
            table_name, catalog=catalog, database=database
        )
        if len(schema) == 0:
            qualified = self._qualified_table_sql(
                table_name, catalog=catalog, database=database
            )
            try:
                if self.uses_api:
                    schema = self._schema_from_api_limit0(f"SELECT * FROM {qualified}")
                else:
                    schema = self._schema_from_trino_limit0(qualified)
            except (
                trino.exceptions.TrinoUserError,
                trino.exceptions.TrinoQueryError,
                trino.exceptions.HttpError,
                DuneQueryError,
            ) as exc:
                if self._is_not_found_error(exc):
                    raise TableNotFound(qualified) from exc
                if isinstance(exc, DuneQueryError):
                    raise
                if self._flip_to_api_on_tier_error(exc):
                    schema = self._schema_from_api_limit0(f"SELECT * FROM {qualified}")
                else:
                    raise self._dune_query_error_from_exc(exc) from None

        return self._normalize_schema(schema)
