from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class DuneQueryError(Exception):
    """Compact error for Dune/Trino query failures at interactive boundaries."""

    message: str
    query_id: str | None = None
    original: BaseException | None = None

    def __str__(self) -> str:
        if self.query_id:
            return f"Dune query error (execution_id={self.query_id}):\n{self.message}"
        return f"Dune query error:\n{self.message}"


@dataclass(eq=False)
class DuneResultTooLargeError(Exception):
    """Raised when a Dune REST result exceeds ``dune_api_max_bytes``."""

    message: str
    total_bytes: int
    max_bytes: int

    def __str__(self) -> str:
        return (
            f"Dune REST result is {self.total_bytes} bytes, "
            f"exceeds dune_api_max_bytes={self.max_bytes}: {self.message}"
        )
