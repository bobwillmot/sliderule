"""Shared helpers for FastAPI main modules across backends."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


FetchAllFn = Callable[..., Any]
GetConnFn = Callable[..., Any]


def fetch_books_shared(fetch_all_fn: FetchAllFn, get_conn_fn: GetConnFn) -> list[dict[str, str]]:
    """Fetch all books sorted by name."""
    with get_conn_fn() as conn:
        rows = fetch_all_fn(
            conn,
            """
            SELECT book_id, book_name
            FROM books
            ORDER BY book_name
            """,
        )

    return [{"book_id": row[0], "book_name": row[1]} for row in rows]


def fetch_instruments_shared(
    fetch_all_fn: FetchAllFn,
    get_conn_fn: GetConnFn,
) -> list[dict[str, str | float | None]]:
    """Fetch all instruments and metadata sorted by key."""
    with get_conn_fn() as conn:
        rows = fetch_all_fn(
            conn,
            """
            SELECT instrument_key,
                   description,
                   exchange,
                   last_close,
                   last_close_date
            FROM instruments
            ORDER BY instrument_key
            """,
        )

    return [
        {
            "instrument_key": row[0],
            "description": row[1],
            "exchange": row[2],
            "last_close": float(row[3]) if row[3] is not None else None,
            "last_close_date": row[4].isoformat() if row[4] is not None else None,
        }
        for row in rows
    ]


def normalize_asof_times(
    valid_time: datetime | None,
    system_time: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Normalize one-sided as-of parameters by defaulting the other to now."""
    if valid_time is not None and system_time is None:
        system_time = datetime.now(timezone.utc)
    elif system_time is not None and valid_time is None:
        valid_time = datetime.now(timezone.utc)
    return valid_time, system_time


def fetch_position_effect_rows(
    fetch_all_fn: FetchAllFn,
    get_conn_fn: GetConnFn,
    book_id: str | None,
    limit: int,
):
    """Fetch position effect rows, optionally filtered by book."""
    with get_conn_fn() as conn:
        if book_id:
            return fetch_all_fn(
                conn,
                """
                SELECT event_book1_id, event_id, book_id, instrument_key, position_type, quantity, created_at
                FROM position_effects
                WHERE book_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (book_id, limit),
            )

        return fetch_all_fn(
            conn,
            """
            SELECT event_book1_id, event_id, book_id, instrument_key, position_type, quantity, created_at
            FROM position_effects
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )


def serialize_position_rows(rows: list[tuple]) -> list[dict[str, Any]]:
    """Serialize position query rows into API payload dictionaries."""
    return [
        {
            "instrument_key": row[0],
            "position_type": row[1],
            "quantity": float(row[2]) if row[2] is not None else 0.0,
            "valid_time": row[3],
        }
        for row in rows
    ]


def serialize_position_effect_rows(rows: list[tuple]) -> list[dict[str, Any]]:
    """Serialize position effect rows into API payload dictionaries."""
    return [
        {
            "event_book1_id": row[0],
            "event_id": str(row[1]),
            "book_id": row[2],
            "instrument_key": row[3],
            "position_type": row[4],
            "quantity": float(row[5]),
            "created_at": row[6],
        }
        for row in rows
    ]
