"""Verbatim Trino SQL fragments for filters (boolean) and projections (typed)."""

from __future__ import annotations

import ibis.expr.datashape as ds
import ibis.expr.datatypes as dt
from ibis.expr.operations.core import Value


class RawSQLBoolean(Value):
    """Scalar boolean that compiles to a parsed Trino SQL expression (verbatim)."""

    sql: str
    dtype = dt.boolean
    shape = ds.scalar


def raw_predicate(sql: str):
    """Return a boolean ibis expression that compiles to the given Trino SQL."""
    return RawSQLBoolean(sql=sql.strip()).to_expr()


class RawSQLScalar(Value):
    """Scalar/columnar value that compiles to parsed Trino SQL (verbatim)."""

    sql: str
    output_dtype: dt.DataType

    @property
    def dtype(self) -> dt.DataType:
        return self.output_dtype

    shape = ds.columnar


def raw_scalar(sql: str, dtype: str | dt.DataType):
    """Return an ibis column expression that compiles to the given Trino SQL."""
    return RawSQLScalar(sql=sql.strip(), output_dtype=dt.dtype(dtype)).to_expr()
