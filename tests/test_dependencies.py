from __future__ import annotations

import importlib.metadata as metadata

import pytest


def test_sqlglot_dune_dialect_importable() -> None:
    """Ensure sqlglot ships the Dune dialect required by ibis-dune."""
    from sqlglot.dialects.dune import Dune  # noqa: F401

    assert Dune is not None


def test_sqlglot_version_meets_minimum() -> None:
    """Ensure installed sqlglot satisfies the ibis-dune pin."""
    version = metadata.version("sqlglot")
    parts = [int(p) for p in version.split(".")[:3]]
    assert tuple(parts) >= (26, 4, 0), f"sqlglot {version} is below 26.4.0"

    if version.startswith("26.32."):
        pytest.fail(f"sqlglot {version} is excluded by ibis-dune pin")
