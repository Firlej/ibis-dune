from __future__ import annotations

import ibis.expr.datatypes as dt
import sqlglot as sg
import sqlglot.expressions as sge
from ibis.backends.sql.compilers.trino import TrinoCompiler
from ibis.backends.sql.datatypes import TrinoType
from ibis.common.collections import FrozenDict
from sqlglot.dialects.dune import Dune

from ibis_dune.ops.hex import HexLiteral
from ibis_dune.ops.raw_sql import RawSQLBoolean, RawSQLScalar


class DuneType(TrinoType):
    """Trino type mapper with Dune-only unknown type strings."""

    dialect = "dune"

    unknown_type_strings = FrozenDict(
        {
            **dict(TrinoType.unknown_type_strings),
            "uint256": dt.Decimal(precision=78, scale=0),
        }
    )


class DuneCompiler(TrinoCompiler):
    """Dune sqlglot compiler with custom visitors for ibis-dune ops."""

    __slots__ = ()

    dialect = Dune
    type_mapper = DuneType

    def visit_RawSQLBoolean(self, op: RawSQLBoolean, *, sql: str):
        return sg.parse_one(sql, read=self.dialect)

    def visit_RawSQLScalar(self, op: RawSQLScalar, *, sql: str, output_dtype):
        del output_dtype
        return sg.parse_one(sql, read=self.dialect)

    def visit_HexLiteral(self, op: HexLiteral, *, value: str):
        hex_body = value[2:] if value.startswith("0x") else value
        return sge.HexString(this=hex_body)


compiler = DuneCompiler()
