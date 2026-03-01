from datetime import datetime, timedelta, timezone
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


def test_cancelling_all_trades_results_in_zero_position():
    """Test that when all trades for an instrument are cancelled, position equals 0."""
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        # Book two trades
        trade1_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                9,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        trade1_id = trade1_row[0]

        trade2_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                4,
                195.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        trade2_id = trade2_row[0]

        # Verify position is 13 (9 + 4)
        positions_before = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )
        positions_before = {(row[0], row[1]): float(row[2]) for row in positions_before}
        assert positions_before[("AAPL", "Shares")] == 13.0

        # Cancel first trade
        book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                9,
                190.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                2,
                trade1_id,
            ),
        )

        # Verify position is now 4 (only uncancelled trade)
        positions_after_1 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )
        positions_after_1 = {(row[0], row[1]): float(row[2]) for row in positions_after_1}
        assert positions_after_1[("AAPL", "Shares")] == 4.0

        # Cancel second trade
        book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                4,
                195.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                2,
                trade2_id,
            ),
        )
        conn.commit()

        # Verify position is 0 (all trades cancelled)
        positions_after_2 = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )
        positions_after_2 = {(row[0], row[1]): float(row[2]) for row in positions_after_2}
        assert positions_after_2[("AAPL", "Shares")] == 0.0


def test_get_positions_endpoint_reflects_cancellations():
    """Test that the /positions endpoint correctly shows 0 when all trades are cancelled."""
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        # Book a trade
        trade_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                10,
                180.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        trade_id = trade_row[0]
        conn.commit()

        # Check position via API
        response = client.get(f"/positions/{book1_id}")
        assert response.status_code == 200
        positions = response.json()
        assert len(positions) == 2

        by_type_and_instrument = {
            (pos["position_type"], pos["instrument_key"]): pos["quantity"]
            for pos in positions
        }
        assert by_type_and_instrument[("Shares", "AAPL")] == 10.0
        assert by_type_and_instrument[("Proceeds", "USD")] == -1800.0

        # Cancel the trade via API
        cancel_payload = {
            "book1_id": book1_id,
            "book2_id": book2_id,
            "book1_side": "BUY",
            "instrument_key": "AAPL",
            "quantity": 10,
            "price": 180.0,
            "currency": "USD",
            "non_economic_data": {"source": "pytest"},
            "valid_time": datetime.now(timezone.utc).isoformat(),
            "created_by": "test_user",
            "type_id": 2,
            "prior_event_id": str(trade_id),
        }
        cancel_response = client.post("/trades", json=cancel_payload)
        assert cancel_response.status_code == 200

        # Check position after cancellation
        response_after = client.get(f"/positions/{book1_id}")
        assert response_after.status_code == 200
        positions_after = response_after.json()
        by_type_and_instrument_after = {
            (pos["position_type"], pos["instrument_key"]): pos["quantity"]
            for pos in positions_after
        }
        assert by_type_and_instrument_after[("Shares", "AAPL")] == 0.0
        assert by_type_and_instrument_after[("Proceeds", "USD")] == 0.0


def test_get_positions_stored_procedure_applies_temporal_filters():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        trade_valid_time = datetime.now(timezone.utc)
        trade_system_cutoff = datetime.now(timezone.utc)

        book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                7,
                180.0,
                "USD",
                Json({"source": "pytest"}),
                trade_valid_time,
                "test_user",
                1,
                None,
            ),
        )
        conn.commit()

        # No temporal filters: includes all recorded rows for the book.
        rows_all = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, None),
        )
        assert rows_all == [
            ("USD", "Proceeds", -1260),
            ("AAPL", "Shares", 7),
        ]

        # System-time cutoff before booking record should exclude the row.
        rows_system_past = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, None, trade_system_cutoff - timedelta(seconds=1)),
        )
        assert rows_system_past == []

        # Valid-time cutoff before trade valid_time should exclude the row.
        rows_valid_past = fetch_all(
            conn,
            """
            SELECT instrument_key, position_type, quantity
            FROM get_positions(%s::text, %s::timestamptz, %s::timestamptz)
            """,
            (book1_id, trade_valid_time - timedelta(seconds=1), None),
        )
        assert rows_valid_past == []


def test_book_trade_writes_position_effects_with_shares_and_proceeds():
    with get_conn() as conn:
        init_db(conn)
        book1_id = ensure_book(conn, "ALPHA_TRADING")
        book2_id = ensure_book(conn, "BETA_CAPITAL")
        ensure_instrument(conn, "AAPL", "Apple Inc")

        trade_row = book_trade(
            conn,
            (
                book1_id,
                book2_id,
                "BUY",
                "AAPL",
                3,
                200.0,
                "USD",
                Json({"source": "pytest"}),
                datetime.now(timezone.utc),
                "test_user",
                1,
                None,
            ),
        )
        conn.commit()

        event_id = trade_row[0]

        effects = fetch_all(
            conn,
            """
            SELECT book_id, instrument_key, position_type, quantity
            FROM position_effects
            WHERE event_id = %s
            ORDER BY book_id, position_type, instrument_key
            """,
            (event_id,),
        )

    assert effects == [
        ("ALPHA_TRADING", "USD", "Proceeds", -600),
        ("ALPHA_TRADING", "AAPL", "Shares", 3),
        ("BETA_CAPITAL", "USD", "Proceeds", 600),
        ("BETA_CAPITAL", "AAPL", "Shares", -3),
    ]


# Tests for position effects delta calculations (business logic)
from decimal import Decimal
from app_abstract.positions import (
    PositionDeltas,
    calculate_open_event_deltas,
    calculate_cancel_event_deltas,
    calculate_novation_event_deltas,
)


class TestOpenEventDeltas:
    """Tests for OpenEvent position delta calculations."""

    def test_buy_event_shares_delta(self):
        """BUY event: book1 gains shares, book2 loses shares."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_open_event_deltas("BUY", qty, price)

        assert deltas.book1_shares_delta == Decimal("100")
        assert deltas.book2_shares_delta == Decimal("-100")
        assert deltas.apply_book1 is True
        assert deltas.apply_book2 is True

    def test_buy_event_proceeds_delta(self):
        """BUY event: book1 pays cash, book2 receives cash."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_open_event_deltas("BUY", qty, price)

        expected_proceeds = -(qty * price)  # -15,050
        assert deltas.book1_proceeds_delta == expected_proceeds
        assert deltas.book2_proceeds_delta == -expected_proceeds

    def test_sell_event_shares_delta(self):
        """SELL event: book1 loses shares, book2 gains shares."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_open_event_deltas("SELL", qty, price)

        assert deltas.book1_shares_delta == Decimal("-100")
        assert deltas.book2_shares_delta == Decimal("100")
        assert deltas.apply_book1 is True
        assert deltas.apply_book2 is True

    def test_sell_event_proceeds_delta(self):
        """SELL event: book1 receives cash, book2 pays cash."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_open_event_deltas("SELL", qty, price)

        expected_proceeds = -(qty * price)  # -15,050
        assert deltas.book1_proceeds_delta == -expected_proceeds
        assert deltas.book2_proceeds_delta == expected_proceeds

    def test_deltas_sum_to_zero(self):
        """Shares and proceeds should sum to zero for both books."""
        qty = Decimal("50")
        price = Decimal("200.00")
        deltas = calculate_open_event_deltas("BUY", qty, price)

        total_shares = deltas.book1_shares_delta + deltas.book2_shares_delta
        total_proceeds = deltas.book1_proceeds_delta + deltas.book2_proceeds_delta

        assert total_shares == Decimal("0")
        assert total_proceeds == Decimal("0")


class TestCancelEventDeltas:
    """Tests for CancelEvent position delta calculations."""

    def test_cancel_reverses_open_buy(self):
        """CancelEvent should reverse a BUY trade."""
        qty = Decimal("100")
        price = Decimal("150.50")

        open_deltas = calculate_open_event_deltas("BUY", qty, price)
        cancel_deltas = calculate_cancel_event_deltas("BUY", qty, price)

        # Cancellation should negate the original
        assert cancel_deltas.book1_shares_delta == -open_deltas.book1_shares_delta
        assert cancel_deltas.book2_shares_delta == -open_deltas.book2_shares_delta
        assert cancel_deltas.book1_proceeds_delta == -open_deltas.book1_proceeds_delta
        assert cancel_deltas.book2_proceeds_delta == -open_deltas.book2_proceeds_delta

    def test_cancel_reverses_open_sell(self):
        """CancelEvent should reverse a SELL trade."""
        qty = Decimal("50")
        price = Decimal("200.00")

        open_deltas = calculate_open_event_deltas("SELL", qty, price)
        cancel_deltas = calculate_cancel_event_deltas("SELL", qty, price)

        assert cancel_deltas.book1_shares_delta == -open_deltas.book1_shares_delta
        assert cancel_deltas.book2_shares_delta == -open_deltas.book2_shares_delta
        assert cancel_deltas.book1_proceeds_delta == -open_deltas.book1_proceeds_delta
        assert cancel_deltas.book2_proceeds_delta == -open_deltas.book2_proceeds_delta

    def test_cancel_deltas_apply_flags(self):
        """CancelEvent should apply to both books."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_cancel_event_deltas("BUY", qty, price)

        assert deltas.apply_book1 is True
        assert deltas.apply_book2 is True


class TestNovationEventDeltas:
    """Tests for NovationEvent position delta calculations."""

    def test_novation_does_not_apply_book1_book2(self):
        """NovationEvent should not apply regular book1/book2 deltas."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_novation_event_deltas("BUY", qty, price)

        assert deltas.apply_book1 is False
        assert deltas.apply_book2 is False
        assert deltas.book1_shares_delta == Decimal("0")
        assert deltas.book1_proceeds_delta == Decimal("0")
        assert deltas.book2_shares_delta == Decimal("0")
        assert deltas.book2_proceeds_delta == Decimal("0")

    def test_novation_old_book2_reversal(self):
        """NovationEvent should reverse old book2 deltas."""
        qty = Decimal("100")
        price = Decimal("150.50")
        deltas = calculate_novation_event_deltas("BUY", qty, price)

        # Old book2 gets reversed (negated) deltas
        assert deltas.old_book2_shares_delta == Decimal("100")
        assert deltas.old_book2_proceeds_delta == -(qty * price)

    def test_novation_old_book2_reversal_sell(self):
        """NovationEvent SELL should reverse old book2 with correct sign."""
        qty = Decimal("50")
        price = Decimal("200.00")
        deltas = calculate_novation_event_deltas("SELL", qty, price)

        # For SELL, the book1_sign is -1, so old_book2_shares_delta = qty * (-1) = -qty
        assert deltas.old_book2_shares_delta == Decimal("-50")
        assert deltas.old_book2_proceeds_delta == qty * price  # Positive proceeds
