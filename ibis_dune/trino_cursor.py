"""Trino cursor cleanup that does not mask query errors with HTTP 405 on close."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from typing import Any

import sqlglot as sg
import trino


class TrinoCursorMixin:
    """Raw SQL cursors with HTTP 405-safe close so query errors are not masked."""

    def _is_cleanup_http_405(self, err: BaseException) -> bool:
        return isinstance(err, trino.exceptions.HttpError) and str(err).startswith(
            "error 405"
        )

    def _close_cursor_best_effort(
        self, cur: Any, *, during_exc: BaseException | None = None
    ) -> None:
        if not getattr(cur, "_query", None):
            return
        try:
            cur.close()
        except Exception as close_err:
            if self._is_cleanup_http_405(close_err):
                return
            if during_exc is not None:
                add_note = getattr(during_exc, "add_note", None)
                if callable(add_note):
                    add_note(
                        "During Trino cursor cleanup, cursor.close() raised a non-405 error: "
                        f"{close_err!r}"
                    )
                return
            raise

    def raw_sql(self, query: str | sg.Expression) -> Any:  # type: ignore[no-untyped-def]
        """Execute raw SQL and return a live cursor."""
        with contextlib.suppress(AttributeError):
            query = query.sql(dialect=self.name, pretty=True)

        con = self.con
        cur = con.cursor()
        try:
            cur.execute(query)
        except Exception:
            if con.transaction is not None:
                con.rollback()
            during_exc = sys.exc_info()[1]
            self._close_cursor_best_effort(cur, during_exc=during_exc)
            raise
        else:
            if con.transaction is not None:
                con.commit()
            return cur

    @contextlib.contextmanager
    def _safe_raw_sql(self, query: str | sg.Expression) -> Iterator[Any]:  # type: ignore[no-untyped-def]
        cur = self.raw_sql(query)
        try:
            yield cur
        finally:
            during_exc = sys.exc_info()[1]
            self._close_cursor_best_effort(cur, during_exc=during_exc)

    @contextlib.contextmanager
    def begin(self):  # type: ignore[no-untyped-def]
        """Yield a transactional cursor with safe close semantics."""
        con = self.con
        cur = con.cursor()
        try:
            yield cur
        except Exception:
            if con.transaction is not None:
                con.rollback()
            during_exc = sys.exc_info()[1]
            self._close_cursor_best_effort(cur, during_exc=during_exc)
            raise
        else:
            if con.transaction is not None:
                con.commit()
        finally:
            during_exc = sys.exc_info()[1]
            self._close_cursor_best_effort(cur, during_exc=during_exc)
