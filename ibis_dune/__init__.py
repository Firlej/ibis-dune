"""Ibis backend for Dune Analytics."""

from __future__ import annotations

from ibis_dune.api_execution import ApiExecutionMixin
from ibis_dune.backend import Backend
from ibis_dune.compiler import DuneCompiler, DuneType, compiler
from ibis_dune.exceptions import DuneQueryError, DuneResultTooLargeError
from ibis_dune.formats import install_rich_formatting, install_uint256_support
from ibis_dune.ops import hex_literal, raw_predicate, raw_scalar
from ibis_dune.schema_fetch import SchemaFetchMixin
from ibis_dune.sql_method import SqlMethodMixin
from ibis_dune.trino_cursor import TrinoCursorMixin

__version__ = "0.1.1"

__all__ = [
    "ApiExecutionMixin",
    "Backend",
    "DuneCompiler",
    "DuneQueryError",
    "DuneResultTooLargeError",
    "DuneType",
    "SchemaFetchMixin",
    "SqlMethodMixin",
    "TrinoCursorMixin",
    "compiler",
    "hex_literal",
    "install_rich_formatting",
    "install_uint256_support",
    "raw_predicate",
    "raw_scalar",
    "__version__",
]
