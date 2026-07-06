from __future__ import annotations

import ibis.expr.datatypes as dt
from ibis_dune.compiler import DuneCompiler, DuneType, compiler
from sqlglot.dialects.dune import Dune


def test_dune_compiler_uses_dune_dialect_and_type_mapper() -> None:
    assert isinstance(compiler, DuneCompiler)
    assert compiler.dialect is Dune
    assert compiler.type_mapper is DuneType


def test_dune_type_maps_uint256() -> None:
    dtype = DuneType.from_string("uint256")
    assert dtype == dt.Decimal(precision=78, scale=0)
