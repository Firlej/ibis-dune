from __future__ import annotations

from typing import Any

import trino
import trino.auth
from dune_client.client import DuneClient
from ibis.backends.trino import Backend as TrinoBackend

from ibis_dune.api_execution import ApiExecutionMixin
from ibis_dune.compiler import compiler as dune_compiler
from ibis_dune.formats import install_rich_formatting, install_uint256_support
from ibis_dune.schema_fetch import SchemaFetchMixin
from ibis_dune.sql_method import SqlMethodMixin
from ibis_dune.trino_cursor import TrinoCursorMixin


class Backend(
    SqlMethodMixin,
    SchemaFetchMixin,
    ApiExecutionMixin,
    TrinoCursorMixin,
    TrinoBackend,
):
    """Ibis backend for Dune Analytics (Trino + automatic REST fallback)."""

    name = "dune"
    compiler = dune_compiler
    supports_create_or_replace = False

    # ---
    # Connection
    # ---

    def do_connect(
        self,
        dune_api_key: str,
        *,
        force_api: bool = False,
        dune_sql_performance: str = "medium",
        dune_api_warning_bytes: int = 1 * 1024 * 1024 * 1024,
        dune_api_max_bytes: int = 4 * 1024 * 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        """Connect to Dune with Trino-first execution and optional REST-first mode.

        Stores ``force_api``, SQL performance tier, and REST byte limits on the
        backend instance. When Trino returns an invalid tier error, execution
        falls back to Dune REST for the session.
        """
        self.dune_api_key = dune_api_key
        self.force_api = force_api
        self._use_api = force_api
        self.dune_sql_performance = dune_sql_performance
        self.dune_api_warning_bytes = dune_api_warning_bytes
        self.dune_api_max_bytes = dune_api_max_bytes
        self.dune_client = DuneClient(api_key=dune_api_key)

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
