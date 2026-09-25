from __future__ import annotations

from typing import Any

import trino
import trino.auth
from ibis.backends.trino import Backend as TrinoBackend

from ibis_dune.compiler import compiler as dune_compiler
from ibis_dune.execution import ExecutionMixin
from ibis_dune.formats import install_rich_formatting, install_uint256_support
from ibis_dune.schema_fetch import SchemaFetchMixin
from ibis_dune.sql_method import SqlMethodMixin
from ibis_dune.trino_cursor import TrinoCursorMixin


class Backend(
    SqlMethodMixin,
    SchemaFetchMixin,
    ExecutionMixin,
    TrinoCursorMixin,
    TrinoBackend,
):
    """Ibis backend for Dune Analytics (paid Trino)."""

    name = "dune"
    compiler = dune_compiler
    supports_create_or_replace = False

    # ---
    # Connection
    # ---

    def do_connect(self, dune_api_key: str, **kwargs: Any) -> None:
        """Connect to Dune Trino with basic auth (``dune`` / API key)."""
        self.dune_api_key = dune_api_key
        super().do_connect(
            user="dune",
            host="trino.api.dune.com",
            port=443,
            http_scheme="https",
            auth=trino.auth.BasicAuthentication("dune", dune_api_key),
            **kwargs,
        )

        install_uint256_support()
        install_rich_formatting()
