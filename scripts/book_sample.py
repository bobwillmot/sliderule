from datetime import datetime, timezone
from decimal import Decimal

from psycopg.types.json import Json

from app_abstract.positions import calculate_open_event_deltas
from app_abstract.shared_db import fetch_one
from app_citus.db import get_conn


def ensure_book(conn, name: str) -> str:
    row = fetch_one(conn, "SELECT book_id FROM books WHERE book_name = %s", (name,))
    if row:
        return row[0]
    row = fetch_one(conn, "SELECT create_book(%s)", (name,))
    return row[0]


def ensure_instrument(conn, key: str, description: str) -> None:
    fetch_one(conn, "SELECT create_instrument(%s, %s)", (key, description))


def book_apple_trade() -> str:
    with get_conn() as conn:
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        # Calculate position deltas using business logic
        quantity = Decimal("5")
        price = Decimal("185.25")
        deltas = calculate_open_event_deltas(
            book1_side="BUY",
            quantity=quantity,
            price=price,
        )

        row = fetch_one(
            conn,
            """
            SELECT book_trade(
                %s::text,
                %s::text,
                %s::text,
                %s::text,
                %s::numeric,
                %s::numeric,
                %s::text,
                %s::jsonb,
                %s::timestamptz,
                %s::text,
                %s::integer,
                %s::uuid,
                %s::numeric,
                %s::numeric,
                %s::numeric,
                %s::numeric,
                %s::numeric,
                %s::numeric,
                %s::boolean,
                %s::boolean
            )
            """,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                5,
                185.25,
                "USD",
                Json({"source": "sample", "note": "few shares"}),
                datetime.now(timezone.utc),
                "sample_user",
                1,
                None,
                deltas.book1_shares_delta,
                deltas.book1_proceeds_delta,
                deltas.book2_shares_delta,
                deltas.book2_proceeds_delta,
                deltas.old_book2_shares_delta,
                deltas.old_book2_proceeds_delta,
                deltas.apply_book1,
                deltas.apply_book2,
            ),
        )
        conn.commit()
        return row[0]


if __name__ == "__main__":
    event_id = book_apple_trade()
    print(f"Booked event_id: {event_id}")
