"""Trino execution with compact ``DuneQueryError`` translation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import trino

from ibis_dune.exceptions import DuneQueryError


class ExecutionMixin:
    """Trino ``execute`` / ``_cursor_batches`` with ``DuneQueryError`` translation."""

    _AUTH_ERROR_HINT = "Dune authentication failed — check dune_api_key"
    _TIER_ERROR_HINT = (
        "Dune Trino access is required (paid API plan). "
        "Free-tier keys can no longer run queries."
    )

    @staticmethod
    def is_invalid_performance_tier_error(exc: BaseException) -> bool:
        """Return whether ``exc`` indicates Trino tier rejection."""
        return "Invalid performance tier" in str(exc)

    @staticmethod
    def _is_auth_error(exc: BaseException) -> bool:
        """Return whether ``exc`` indicates invalid or missing Dune API credentials."""
        message = getattr(exc, "message", None) or str(exc)
        lower = message.lower()
        return (
            "401" in message
            or "403" in message
            or "unauthorized" in lower
            or "invalid api key" in lower
            or "authentication" in lower
        )

    @classmethod
    def _dune_query_error_from_exc(cls, exc: BaseException) -> DuneQueryError:
        """Wrap ``exc`` in ``DuneQueryError``, with auth or paid-plan hints when applicable."""
        if isinstance(exc, DuneQueryError):
            return exc
        if cls.is_invalid_performance_tier_error(exc):
            message = getattr(exc, "message", None) or str(exc)
            return DuneQueryError(
                message=f"{cls._TIER_ERROR_HINT}\n{message}",
                query_id=getattr(exc, "query_id", None),
                original=exc,
            )
        if cls._is_auth_error(exc):
            if isinstance(exc, trino.exceptions.TrinoQueryError):
                return DuneQueryError(
                    message=f"{cls._AUTH_ERROR_HINT}\n{exc.message}",
                    query_id=getattr(exc, "query_id", None),
                    original=exc,
                )
            return DuneQueryError(
                message=f"{cls._AUTH_ERROR_HINT}\n{exc}",
                original=exc,
            )
        return cls._to_dune_query_error(exc)

    @staticmethod
    def _to_dune_query_error(exc: BaseException) -> DuneQueryError:
        """Wrap a Trino failure in a compact ``DuneQueryError``."""
        if isinstance(exc, trino.exceptions.TrinoQueryError):
            return DuneQueryError(
                message=exc.message,
                query_id=getattr(exc, "query_id", None),
                original=exc,
            )
        if isinstance(exc, trino.exceptions.HttpError):
            return DuneQueryError(message=str(exc), original=exc)
        raise TypeError(f"expected TrinoQueryError or HttpError, got {type(exc)!r}")

    def execute(  # type: ignore[no-untyped-def]
        self,
        expr,
        /,
        *,
        params: Mapping | None = None,
        limit: int | str | None = None,
        **kwargs: Any,
    ):
        """Execute via Trino and wrap query failures as ``DuneQueryError``."""
        try:
            return super().execute(expr, params=params, limit=limit, **kwargs)  # type: ignore[misc]
        except (trino.exceptions.TrinoQueryError, trino.exceptions.HttpError) as e:
            raise self._dune_query_error_from_exc(e) from None

    def _cursor_batches(  # type: ignore[no-untyped-def]
        self,
        expr,
        params: Mapping | None = None,
        limit: int | str | None = None,
        chunk_size: int = 1 << 20,
    ) -> Iterable[list]:
        """Yield Trino cursor batches; wrap query failures as ``DuneQueryError``."""
        try:
            yield from super()._cursor_batches(  # type: ignore[misc]
                expr, params=params, limit=limit, chunk_size=chunk_size
            )
        except (trino.exceptions.TrinoQueryError, trino.exceptions.HttpError) as e:
            raise self._dune_query_error_from_exc(e) from None
