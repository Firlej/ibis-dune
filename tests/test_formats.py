from __future__ import annotations

import ibis
import ibis.expr.datatypes as dt
import pyarrow as pa
import pytest
from ibis.expr.types import _rich as ibis_rich
from ibis.formats.pyarrow import PyArrowType
from ibis_dune import Backend
from ibis_dune.formats import (
    _ARROW_DECIMAL_STRING_MIN_PRECISION,
    install_rich_formatting,
    install_uint256_support,
    is_large_decimal,
)
from rich.text import Text

from tests.helpers import bound_table


@pytest.fixture
def uint256_dtype() -> dt.Decimal:
    return dt.Decimal(precision=78, scale=0)


def test_is_large_decimal_threshold() -> None:
    assert is_large_decimal(dt.Decimal(precision=78, scale=0)) is True
    assert is_large_decimal(dt.Decimal(precision=39, scale=0)) is True
    assert is_large_decimal(dt.Decimal(precision=38, scale=0)) is False
    assert _ARROW_DECIMAL_STRING_MIN_PRECISION == 39


def test_sum_dtype_over_uint256(
    offline_backend: Backend, uint256_dtype: dt.Decimal
) -> None:
    t = bound_table(
        offline_backend,
        "t",
        "db",
        schema=ibis.schema({"x": uint256_dtype}),
    )
    assert str(t.x.sum().type()) == "decimal(78, 0)"


def test_mean_dtype_over_uint256(
    offline_backend: Backend, uint256_dtype: dt.Decimal
) -> None:
    t = bound_table(
        offline_backend,
        "t",
        "db",
        schema=ibis.schema({"x": uint256_dtype}),
    )
    assert t.x.mean().type().is_floating()


def test_pyarrow_maps_large_decimal_to_string(uint256_dtype: dt.Decimal) -> None:
    install_uint256_support()
    pa_type = PyArrowType.from_ibis(uint256_dtype)
    assert pa.types.is_string(pa_type)


def test_pyarrow_keeps_decimal38_as_decimal() -> None:
    install_uint256_support()
    dtype = dt.Decimal(precision=38, scale=0)
    pa_type = PyArrowType.from_ibis(dtype)
    assert pa.types.is_decimal(pa_type)


def test_format_dtype_shows_uint256_label(uint256_dtype: dt.Decimal) -> None:
    install_rich_formatting()
    label = ibis_rich.format_dtype(uint256_dtype, max_string=80)
    assert isinstance(label, Text)
    assert label.plain == "uint256"


def test_format_values_renders_uint256_strings(uint256_dtype: dt.Decimal) -> None:
    install_rich_formatting()
    rendered = ibis_rich.format_values(uint256_dtype, ["9488020000000"])
    assert len(rendered) == 1
    assert rendered[0].plain == "9488020000000"


def test_format_values_renders_binary_as_hex() -> None:
    install_rich_formatting()
    rendered = ibis_rich.format_values(dt.binary, [b"\xde\xad\xbe\xef"])
    assert len(rendered) == 1
    assert rendered[0].plain == "0xdeadbeef"


def test_install_functions_are_idempotent(offline_backend: Backend) -> None:
    install_uint256_support()
    install_uint256_support()
    install_rich_formatting()
    install_rich_formatting()

    t = bound_table(
        offline_backend,
        "t",
        "db",
        schema=ibis.schema({"x": dt.Decimal(precision=78, scale=0)}),
    )
    assert str(t.x.sum().type()) == "decimal(78, 0)"
    assert ibis_rich.format_dtype(t.x.type(), max_string=80).plain == "uint256"


def test_do_connect_installs_formats() -> None:
    backend = Backend().connect(dune_api_key="offline-formats-test")
    t = bound_table(
        backend,
        "t",
        "db",
        schema=ibis.schema({"x": dt.Decimal(precision=78, scale=0)}),
    )
    assert str(t.x.sum().type()) == "decimal(78, 0)"
    assert PyArrowType.from_ibis(dt.Decimal(precision=78, scale=0)) == pa.string()
    assert backend.name == "dune"
