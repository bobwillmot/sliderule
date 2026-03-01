from datetime import datetime, timezone
from decimal import Decimal

import pytest
from psycopg.types.json import Json
from fastapi.testclient import TestClient

from app_abstract.positions import (
    calculate_open_event_deltas,
    calculate_cancel_event_deltas,
    calculate_novation_event_deltas,
)
from app_abstract.shared_db import fetch_all, fetch_one, run_sql
from app_citus.db import get_conn
from app_citus.main import app
from pathlib import Path

client = TestClient(app)


def init_db(conn) -> None:
    base_dir = Path(__file__).resolve().parents[1]
    schema_sql = (base_dir / "sql" / "schema.sql").read_text()
    seed_sql = (base_dir / "sql" / "seed_reference_data.sql").read_text()
    procs_sql = (base_dir / "sql" / "procs.sql").read_text()
    # Drop functions and tables to ensure clean state
    run_sql(conn, "DROP FUNCTION IF EXISTS book_trade(text, text, text, text, numeric, numeric, text, jsonb, timestamptz, text, integer, uuid) CASCADE;")
    run_sql(conn, "DROP FUNCTION IF EXISTS book_trade(text, text, text, text, numeric, numeric, text, jsonb, timestamptz, text, integer, uuid, numeric, numeric, numeric, numeric, numeric, numeric, boolean, boolean) CASCADE;")
    run_sql(conn, "DROP FUNCTION IF EXISTS get_positions(text, timestamptz, timestamptz);")
    run_sql(conn, "DROP TABLE IF EXISTS position_effects CASCADE;")
    run_sql(conn, "DROP TABLE IF EXISTS positions CASCADE;")
    run_sql(conn, "DROP TABLE IF EXISTS trade_events CASCADE;")
    run_sql(conn, "DROP TABLE IF EXISTS trade_event_types CASCADE;")
    run_sql(conn, "DROP TABLE IF EXISTS instruments CASCADE;")
    run_sql(conn, "DROP TABLE IF EXISTS books CASCADE;")
    run_sql(conn, schema_sql)
    run_sql(conn, seed_sql)
    run_sql(conn, procs_sql)


def ensure_book(conn, name: str) -> str:
    row = fetch_one(conn, "SELECT book_id FROM books WHERE book_name = %s", (name,))
    if row:
        return row[0]
    row = fetch_one(conn, "SELECT create_book(%s)", (name,))
    return row[0]


def ensure_instrument(conn, key: str, description: str) -> None:
    fetch_one(conn, "SELECT create_instrument(%s, %s)", (key, description))


def book_trade(conn, payload):
    """
    Call book_trade SQL function with pre-calculated deltas.

    Payload format: (book1_id, book2_id, book1_side, instrument_key, quantity, price, currency,
                     non_economic_data, valid_time, created_by, type_id, correction_of_or_none)

    This helper calculates position deltas using app/positions logic before calling SQL.
    """
    book1_id, book2_id, book1_side, instrument_key, quantity, price, currency, _, _, _, type_id, _ = payload

    # Calculate deltas based on trade type
    if type_id == 1:  # OpenEvent
        deltas = calculate_open_event_deltas(book1_side, Decimal(str(quantity)), Decimal(str(price)))
    elif type_id == 2:  # CancelEvent
        deltas = calculate_cancel_event_deltas(book1_side, Decimal(str(quantity)), Decimal(str(price)))
    elif type_id == 5:  # NovationEvent
        deltas = calculate_novation_event_deltas(book1_side, Decimal(str(quantity)), Decimal(str(price)))
    else:
        raise ValueError(f"Unsupported type_id: {type_id}")

    # Convert deltas to numeric values for SQL
    extended_payload = payload + (
        deltas.book1_shares_delta,
        deltas.book1_proceeds_delta,
        deltas.book2_shares_delta,
        deltas.book2_proceeds_delta,
        deltas.old_book2_shares_delta,
        deltas.old_book2_proceeds_delta,
        deltas.apply_book1,
        deltas.apply_book2,
    )

    return fetch_one(
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
        extended_payload,
    )


def test_book_apple_trade():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                5,
                185.25,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        conn.commit()

        event_id = row[0]

        events = fetch_all(
            conn,
            "SELECT book1_id, book2_id, book1_side, quantity, instrument_key FROM trade_events WHERE event_id = %s",
            (event_id,),
        )

        positions = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )

        positions_book2 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book2_id, None, None),
        )

    positions = {(row[0], row[1]): float(row[2]) for row in positions}
    positions_book2 = {(row[0], row[1]): float(row[2]) for row in positions_book2}

    assert len(events) == 1
    assert events[0][0] == "ALPHA_TRADING"
    assert events[0][1] == "BETA_CAPITAL"
    assert events[0][2] == "BUY"
    assert events[0][3] == 5
    assert events[0][4] == "AAPL"
    assert positions[("AAPL", "Shares")] == 5.0
    assert positions[("USD", "Proceeds")] == -(5.0 * 185.25)
    assert positions_book2[("AAPL", "Shares")] == -5.0
    assert positions_book2[("USD", "Proceeds")] == (5.0 * 185.25)


def test_cancel_trade_reverses_positions():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        open_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        open_event_id = open_row[0]

        cancel_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest", "cancel": True}),
                datetime.now(timezone.utc),
                "test_user",
                2,
                open_event_id,
            ),
        )
        conn.commit()

        cancel_event_id = cancel_row[0]

        events = fetch_all(
            conn,
            "SELECT type_id, correction_of FROM trade_events WHERE event_id IN (%s, %s)",
            (open_event_id, cancel_event_id),
        )
        positions = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )

        positions_book2 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book2_id, None, None),
        )

    positions = {(row[0], row[1]): float(row[2]) for row in positions}
    positions_book2 = {(row[0], row[1]): float(row[2]) for row in positions_book2}
    assert sorted([row[0] for row in events]) == [1, 2]
    assert positions[("AAPL", "Shares")] == 0.0
    assert positions[("USD", "Proceeds")] == 0.0
    assert positions_book2[("AAPL", "Shares")] == 0.0
    assert positions_book2[("USD", "Proceeds")] == 0.0


def test_cancel_requires_prior_trade_reference():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        with pytest.raises(Exception):
            book_trade(
                conn,
                (
                    book1_id,
                    book2_id,
                    "BUY",
                    "AAPL",
                    5,
                    180.0,
                    "USD",
                    Json({"source": "pytest"}),
                    datetime.now(timezone.utc),
                    "test_user",
                    2,
                    None,
                ),
            )


def test_amend_and_partial_terminate_are_rejected():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        open_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        open_event_id = open_row[0]

        with pytest.raises(Exception):
            book_trade(
                conn,
                (
                    book1_id,
                    book2_id,
                    "BUY",
                    "AAPL",
                    14,
                    191.0,
                    "USD",
                    Json({"source": "pytest", "amend": True}),
                    datetime.now(timezone.utc),
                    "test_user",
                    3,
                    open_event_id,
                ),
            )

        with pytest.raises(Exception):
            book_trade(
                conn,
                (
                    book1_id,
                    book2_id,
                    "BUY",
                    "AAPL",
                    3,
                    190.0,
                    "USD",
                    Json({"source": "pytest", "partial_terminate": True}),
                    datetime.now(timezone.utc),
                    "test_user",
                    4,
                    open_event_id,
                ),
            )


def test_novation_moves_counterparty_exposure_to_new_book2():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        old_book2_id = ensure_book(conn, "BETA_CAPITAL")
        new_book2_id = ensure_book(conn, "GAMMA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        open_row = book_trade(
            conn,
            (
                book1_id,
                old_book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        open_event_id = open_row[0]

        book_trade(
            conn,
            (
                book1_id,
                new_book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest", "novation": True}),
                datetime.now(timezone.utc),
                "test_user",
                5,
                open_event_id,
            ),
        )
        conn.commit()

        positions_book1 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )
        positions_old_book2 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (old_book2_id, None, None),
        )
        positions_new_book2 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (new_book2_id, None, None),
        )

    positions_book1 = {(row[0], row[1]): float(row[2]) for row in positions_book1}
    positions_old_book2 = {(row[0], row[1]): float(row[2]) for row in positions_old_book2}
    positions_new_book2 = {(row[0], row[1]): float(row[2]) for row in positions_new_book2}

    assert positions_book1[("AAPL", "Shares")] == 10.0
    assert positions_old_book2[("AAPL", "Shares")] == 0.0
    assert positions_new_book2[("AAPL", "Shares")] == -10.0


def test_novation_rejects_new_book2_same_as_book1():
    """Novation should reject when new book2_id is the same as book1_id."""
    client = TestClient(app)
    with get_conn() as conn:
        init_db(conn)
        book_id = ensure_book(conn, "ALPHA_TRADING")
        old_book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        open_row = book_trade(
            conn,
            (
                book_id,
                old_book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        open_event_id = open_row[0]
        conn.commit()

    # Try to novate to the same book as book1
    response = client.post(
        "/trades",
        json={
            "book1_id": book_id,
            "book2_id": book_id,  # Same as book1_id - should fail
            "book1_side": "BUY",
            "instrument_key": "AAPL",
            "quantity": 10,
            "price": 190.0,
            "currency": "USD",
            "valid_time": datetime.now(timezone.utc).isoformat(),
            "type_id": 5,
            "prior_event_id": str(open_event_id),
        }
    )
    assert response.status_code == 422
    assert "book2_id cannot be the same as book1_id" in response.text


def test_novation_rejects_new_book2_same_as_prior_book2():
    """Novation should reject when new book2_id is the same as prior book2_id."""
    client = TestClient(app)
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        old_book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        open_row = book_trade(
            conn,
            (
                book1_id,
                old_book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        open_event_id = open_row[0]
        conn.commit()

    # Try to novate back to the same book2 - should fail
    response = client.post(
        "/trades",
        json={
            "book1_id": book1_id,
            "book2_id": old_book2_id,  # Same as prior book2_id - should fail
            "book1_side": "BUY",
            "instrument_key": "AAPL",
            "quantity": 10,
            "price": 190.0,
            "currency": "USD",
            "valid_time": datetime.now(timezone.utc).isoformat(),
            "type_id": 5,
            "prior_event_id": str(open_event_id),
        }
    )
    assert response.status_code == 400
    assert "cannot be the same as prior book2_id" in response.text


def test_cancellable_trades_endpoint_excludes_cancel_events():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        open_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        open_event_id = open_row[0]

        book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                10,
                190.0,
                "USD",
                Json({"source": "pytest", "cancel": True}),
                datetime.now(timezone.utc),
                "test_user",
                2,
                open_event_id,
            ),
        )
        conn.commit()

    response = client.get(f"/trades/book/{book1_id}/cancellable")
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert all(event["type_id"] != 2 for event in payload)
    assert any(event["event_id"] == str(open_event_id) for event in payload)
