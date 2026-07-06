"""Dune-specific ibis format hooks (uint256 support and rich preview).

Ibis exposes no per-backend hooks for reduction dtype inference, PyArrow type
mapping, or rich rendering. These registrations are process-wide but only
matter for Dune ``Decimal(78, 0)`` / large decimals and Dune binary previews.
They are applied idempotently from ``Backend.do_connect()`` and via the public
``install_uint256_support()`` / ``install_rich_formatting()`` entry points.
"""

from __future__ import annotations

import binascii
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Decimals at or above this precision map to PyArrow string (uint256 / Dune ints).
_ARROW_DECIMAL_STRING_MIN_PRECISION = 39

_UINT256_DECIMAL_COLOR = "light_sea_green"
_BINARY_HEX_COLOR = "slate_blue3"

_INSTALLED_REDUCTIONS: set[str] = set()
_RICH_DECIMAL_INSTALLED = False
_RICH_BINARY_INSTALLED = False


def _already_patched(fn: Any) -> bool:
    return getattr(fn, "__ibis_dune_patched__", False)


def _mark_patched(fn: F) -> F:
    fn.__ibis_dune_patched__ = True  # type: ignore[attr-defined]
    return fn


# ---
# Dtype helpers
# ---


def is_large_decimal(dtype: Any) -> bool:
    """Return whether ``dtype`` should use a string PyArrow surrogate."""
    import ibis.expr.datatypes as dt

    return (
        isinstance(dtype, dt.Decimal)
        and dtype.precision is not None
        and dtype.precision >= _ARROW_DECIMAL_STRING_MIN_PRECISION
    )


def _is_uint256_surrogate(dtype: Any) -> bool:
    import ibis.expr.datatypes as dt

    return isinstance(dtype, dt.Decimal) and dtype.precision == 78 and dtype.scale == 0


# ---
# Reduction dtype inference
# ---


def _patch_reduction_dtype(op_name: str, default_fn: Callable[..., Any]) -> None:
    from ibis.expr.operations import reductions

    op_cls = getattr(reductions, op_name, None)
    if op_cls is None:
        return

    dtype_field = getattr(op_cls, "__attributes__", {}).get("dtype")
    if dtype_field is None:
        return

    if _already_patched(getattr(dtype_field, "default", None)):
        return

    object.__setattr__(dtype_field, "default", _mark_patched(default_fn))


def _install_reduction_dtypes() -> None:
    import ibis.expr.datatypes as dt

    if "Sum" not in _INSTALLED_REDUCTIONS:

        def dtype_with_integer_decimal_scale(self):  # type: ignore[no-untyped-def]
            dtype = self.arg.dtype
            if dtype.is_boolean():
                return dt.int64
            if dtype.is_integer():
                return dt.int64
            if dtype.is_unsigned_integer():
                return dt.uint64
            if dtype.is_floating():
                return dt.float64
            if dtype.is_decimal():
                precision = (
                    max(dtype.precision, 38) if dtype.precision is not None else None
                )
                scale = (
                    0
                    if dtype.scale == 0
                    else (max(dtype.scale, 2) if dtype.scale is not None else None)
                )
                return dt.Decimal(precision=precision, scale=scale)
            raise TypeError(f"Cannot compute sum of {dtype} values")

        _patch_reduction_dtype("Sum", dtype_with_integer_decimal_scale)
        _INSTALLED_REDUCTIONS.add("Sum")

    if "Mean" not in _INSTALLED_REDUCTIONS:

        def dtype_mean_uint256_float64(self):  # type: ignore[no-untyped-def]
            dtype = self.arg.dtype
            if dtype.is_boolean():
                return dt.float64
            if dtype.is_decimal() and dtype.scale == 0:
                return dt.float64
            return dt.higher_precedence(dtype, dt.float64)

        _patch_reduction_dtype("Mean", dtype_mean_uint256_float64)
        _INSTALLED_REDUCTIONS.add("Mean")


# ---
# PyArrow preview mapping
# ---


def _install_pyarrow_decimal_string() -> None:
    from ibis.formats.pyarrow import PyArrowType

    if _already_patched(PyArrowType.from_ibis):
        return

    original_from_ibis = PyArrowType.from_ibis

    def from_ibis_with_decimal_preview(dtype):  # type: ignore[no-untyped-def]
        if is_large_decimal(dtype):
            import pyarrow as pa

            return pa.string()
        return original_from_ibis(dtype)

    PyArrowType.from_ibis = staticmethod(  # type: ignore[method-assign]
        _mark_patched(from_ibis_with_decimal_preview)
    )


# ---
# Rich preview rendering
# ---


def _install_decimal_format() -> None:
    global _RICH_DECIMAL_INSTALLED
    if _RICH_DECIMAL_INSTALLED:
        return

    import ibis.expr.datatypes as dt
    from ibis.expr.types import _rich
    from rich.text import Text

    @_rich.format_values.register(dt.Decimal)  # type: ignore[misc]
    def _(dtype, values, **fmt_kwargs):  # type: ignore[no-untyped-def]
        if dtype.scale is not None:
            fmt = f"{{:.{dtype.scale}f}}"
            style = (
                f"bold {_UINT256_DECIMAL_COLOR}"
                if _is_uint256_surrogate(dtype)
                else "bold cyan"
            )
            out = []
            for v in values:
                if v is None:
                    out.append(Text("None"))
                    continue
                if isinstance(v, str):
                    out.append(Text.styled(v, style))
                    continue
                try:
                    out.append(Text.styled(fmt.format(v), style))
                except Exception:
                    out.append(Text.styled(str(v), style))
            return out

        if _is_uint256_surrogate(dtype):
            style = f"bold {_UINT256_DECIMAL_COLOR}"
            out = []
            for v in values:
                if v is None:
                    out.append(Text("None"))
                    continue
                if isinstance(v, str):
                    out.append(Text.styled(v, style))
                    continue
                try:
                    out.append(Text.styled(str(float(v)), style))
                except Exception:
                    out.append(Text.styled(str(v), style))
            return out
        return _rich.format_values(dt.float64, [float(v) for v in values], **fmt_kwargs)

    _RICH_DECIMAL_INSTALLED = True


def _install_binary_hex() -> None:
    global _RICH_BINARY_INSTALLED
    if _RICH_BINARY_INSTALLED:
        return

    import ibis.expr.datatypes as dt
    from ibis.expr.types import _rich
    from rich.text import Text

    @_rich.format_values.register(dt.Binary)  # type: ignore[misc]
    def _(dtype, values, **fmt_kwargs):  # type: ignore[no-untyped-def]
        del fmt_kwargs
        out = []
        for v in values:
            if v is None:
                out.append(Text.styled("~", "dim"))
                continue

            if isinstance(v, memoryview):
                v = v.tobytes()

            if isinstance(v, bytes | bytearray):
                try:
                    s = bytes(v).decode("utf-8")
                except Exception:
                    s = "0x" + binascii.hexlify(bytes(v)).decode("ascii")
                else:
                    if not s.startswith("0x"):
                        s = "0x" + binascii.hexlify(bytes(v)).decode("ascii")
                out.append(Text.styled(s, _BINARY_HEX_COLOR))
                continue

            out.append(Text.styled(str(v), _BINARY_HEX_COLOR))

        return out

    _RICH_BINARY_INSTALLED = True


def _install_uint256_dtype_label() -> None:
    from ibis.expr.types import _rich
    from rich.text import Text

    if _already_patched(_rich.format_dtype):
        return

    original_format_dtype = _rich.format_dtype

    def format_dtype_with_uint256(dtype, max_string: int) -> Text:  # type: ignore[no-untyped-def]
        if _is_uint256_surrogate(dtype):
            return Text.styled("uint256", "dim")
        return original_format_dtype(dtype, max_string)

    _rich.format_dtype = _mark_patched(format_dtype_with_uint256)  # type: ignore[assignment]


# ---
# Public installers
# ---


def install_uint256_support() -> None:
    """Idempotently teach ibis to handle Dune uint256 (``Decimal(78, 0)``)."""
    _install_reduction_dtypes()
    _install_pyarrow_decimal_string()


def install_rich_formatting() -> None:
    """Idempotently register Dune-flavored rich preview rendering."""
    _install_decimal_format()
    _install_binary_hex()
    _install_uint256_dtype_label()
