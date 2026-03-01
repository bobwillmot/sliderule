"""Common backend adapter base classes for API app composition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable

from app_abstract.shared_main_utils import (
    fetch_books_shared,
    fetch_instruments_shared,
    fetch_position_effect_rows,
    normalize_asof_times,
    serialize_position_effect_rows,
    serialize_position_rows,
)


class SqlBackendAdapter(ABC):
    """Base adapter for SQL-backed sliderule API deployments."""

    backend_id: str
    app_title: str
    startup_label: str
    COUNTS_SQL = """
        SELECT (SELECT count(*) FROM books) AS book_count,
               (SELECT count(*) FROM instruments) AS instrument_count,
               (SELECT count(*) FROM trade_events) AS trade_event_count
    """
    FUNCTION_POSITIONS_SQL = """
        SELECT instrument_key,
               position_type,
               quantity,
               valid_time
        FROM get_positions(
            %(book_id)s::text,
            %(valid_time)s::timestamptz,
            %(system_time)s::timestamptz
        )
    """

    def __init__(
        self,
        backend_id: str,
        app_title: str,
        startup_label: str,
        fetch_all_fn: Callable[..., Any],
        fetch_one_fn: Callable[..., Any],
        get_conn_fn: Callable[..., Any],
        trade_service: Any,
    ) -> None:
        self.backend_id = backend_id
        self.app_title = app_title
        self.startup_label = startup_label
        self.fetch_all = fetch_all_fn
        self.fetch_one = fetch_one_fn
        self.get_conn = get_conn_fn
        self.trade_service = trade_service

    def fetch_books(self) -> list[dict[str, str]]:
        """Fetch all books from the backend."""
        return fetch_books_shared(self.fetch_all, self.get_conn)

    def fetch_instruments(self) -> list[dict[str, str | float | None]]:
        """Fetch all instruments from the backend."""
        return fetch_instruments_shared(self.fetch_all, self.get_conn)

    def get_position_effects(self, book_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch and serialize position effect rows."""
        rows = fetch_position_effect_rows(self.fetch_all, self.get_conn, book_id, limit)
        return serialize_position_effect_rows(rows)

    def fetch_entity_counts(self, conn: Any | None = None) -> dict[str, int]:
        """Return canonical row counts for books, instruments, and trade events."""
        if conn is not None:
            counts = self.fetch_one(conn, self.COUNTS_SQL)
        else:
            with self.get_conn() as owned_conn:
                counts = self.fetch_one(owned_conn, self.COUNTS_SQL)

        return {
            "books": int(counts[0]),
            "instruments": int(counts[1]),
            "trade_events": int(counts[2]),
        }

    @staticmethod
    def build_single_node_cluster_status(backend: str, counts: dict[str, int], mode: str = "single-node") -> dict[str, Any]:
        """Build a standard single-node backend cluster status payload."""
        return {
            "backend": backend,
            "mode": mode,
            "counts": counts,
        }

    @staticmethod
    def build_internal_sharding_status(backend: str, note: str) -> dict[str, str]:
        """Build a standard payload for backends with internal sharding."""
        return {
            "backend": backend,
            "sharding": "internal",
            "note": note,
        }

    def get_positions(
        self,
        book_id: str,
        valid_time: datetime | None = None,
        system_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and serialize positions for a book."""
        valid_time, system_time = normalize_asof_times(valid_time, system_time)

        with self.get_conn() as conn:
            rows = self.fetch_all(
                conn,
                self.get_positions_sql(),
                {
                    "book_id": book_id,
                    "valid_time": valid_time,
                    "system_time": system_time,
                },
            )

        return serialize_position_rows(rows)

    def get_positions_sql(self) -> str:
        """Return SQL used by `get_positions`; override only when backend differs."""
        return self.FUNCTION_POSITIONS_SQL

    @abstractmethod
    def get_cluster_status(self) -> dict[str, Any]:
        """Return backend cluster/status payload."""

    @abstractmethod
    def get_shard_status(self) -> dict[str, Any]:
        """Return backend shard/distribution payload."""
