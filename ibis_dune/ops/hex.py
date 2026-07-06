from __future__ import annotations

import ibis.expr.datashape as ds
import ibis.expr.datatypes as dt
import ibis.expr.operations as ops
import ibis.expr.types as ir


class HexScalar(ir.StringScalar):
    def __repr__(self) -> str:
        return self.op().value

    def __deferred_repr__(self) -> str:
        return self.op().value


ir.HexScalar = HexScalar  # type: ignore[attr-defined]


class HexType(dt.Primitive):
    scalar = "HexScalar"
    column = "StringColumn"

    def castable(self, to, **kwargs):
        return True


class HexLiteral(ops.Value):
    """Custom hex string literal operation compiled with Dune HEX syntax."""

    value: str
    dtype = HexType()
    shape = ds.scalar


def hex_literal(hex_str: str):
    """Create a validated ``HexLiteral`` expression from a hex string."""
    normalized = hex_str.strip().lower()
    body = normalized[2:] if normalized.startswith("0x") else normalized

    if body and len(body) % 2 != 0:
        raise ValueError(f"invalid hex literal {hex_str!r}")
    if any(ch not in "0123456789abcdef" for ch in body):
        raise ValueError(f"invalid hex literal {hex_str!r}")

    return HexLiteral(value=normalized).to_expr()
