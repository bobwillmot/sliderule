"""Test cancel trade via API endpoint."""
from datetime import datetime, timezone
import time
from uuid import UUID

from fastapi.testclient import TestClient

from app_abstract.shared_db import fetch_all, run_sql
from app_citus.db import get_conn
from app_citus.main import app
from pathlib import Path

client = TestClient(app)


def init_db(conn) -> None:
    base_dir = Path(__file__).resolve().parents[1]
    schema_sql = (base_dir / "sql" / "schema.sql").read_text()
    seed_sql = (base_dir / "sql" / "seed_reference_data.sql").read_text()
    procs_sql = (base_dir / "sql" / "procs.sql").read_text()
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


def get_position_quantity(positions, instrument_key: str, position_type: str = "Shares") -> float:
    for position in positions:
        if position["instrument_key"] == instrument_key and position["position_type"] == position_type:
            return float(position["quantity"])
    raise AssertionError(f"Missing position for {position_type}/{instrument_key}: {positions}")


def test_api_cancel_trade_creates_event_and_updates_positions():
    """Test that canceling a trade via API creates a cancel event and updates positions."""
    with get_conn() as conn:
        init_db(conn)

    # Book an open trade via API
    open_trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 15,
        "price": 175.50,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None
    }

    open_response = client.post("/trades", json=open_trade_payload)
    assert open_response.status_code == 200
    open_event_id = open_response.json()["event_id"]

    # Verify open trade created
    with get_conn() as conn:
        open_events = fetch_all(
            conn,
            "SELECT event_id, type_id, correction_of FROM trade_events WHERE event_id = %s",
            (open_event_id,),
        )
        assert len(open_events) == 1
        assert open_events[0][1] == 1  # type_id should be 1 (open)
        assert open_events[0][2] is None  # no correction_of

    # Fetch positions before cancel
    positions_response = client.get("/positions/ALPHA_TRADING")
    assert positions_response.status_code == 200
    positions_before = positions_response.json()
    assert get_position_quantity(positions_before, "AAPL", "Shares") == 15.0
    assert get_position_quantity(positions_before, "USD", "Proceeds") == -(15.0 * 175.50)

    # Cancel the trade via API
    cancel_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 15,
        "price": 175.50,
        "currency": "USD",
        "non_economic_data": {"source": "test", "cancel": True},
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 2,

        "prior_event_id": open_event_id
    }

    cancel_response = client.post("/trades", json=cancel_payload)
    assert cancel_response.status_code == 200
    cancel_event_id = cancel_response.json()["event_id"]

    # Verify cancel event created with correct references
    with get_conn() as conn:
        cancel_events = fetch_all(
            conn,
            "SELECT event_id, type_id, correction_of FROM trade_events WHERE event_id = %s",
            (cancel_event_id,),
        )
        assert len(cancel_events) == 1
        assert cancel_events[0][1] == 2  # type_id should be 2 (cancel)
        assert cancel_events[0][2] == UUID(open_event_id)  # correction_of should reference open trade as UUID

    # Verify positions are reversed to zero
    positions_response = client.get("/positions/ALPHA_TRADING")
    assert positions_response.status_code == 200
    positions_after = positions_response.json()
    assert get_position_quantity(positions_after, "AAPL", "Shares") == 0.0
    assert get_position_quantity(positions_after, "USD", "Proceeds") == 0.0

    # Verify trades by book endpoint shows both events
    trades_response = client.get("/trades/book/ALPHA_TRADING")
    assert trades_response.status_code == 200
    trades = trades_response.json()
    assert len(trades) == 2  # both open and cancel events
    event_types = sorted([t["type_id"] for t in trades])
    assert event_types == [1, 2]


def test_positions_support_valid_and_system_time_asof():
    """Test point-in-time positions filtered by valid and system times."""
    with get_conn() as conn:
        init_db(conn)

    base_valid = datetime.now(timezone.utc)
    trade_1 = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 180.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": base_valid.isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    response_1 = client.post("/trades", json=trade_1)
    assert response_1.status_code == 200

    system_cutoff = datetime.now(timezone.utc)
    time.sleep(0.05)

    trade_2 = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 7,
        "price": 182.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": (base_valid.replace(microsecond=0)).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    response_2 = client.post("/trades", json=trade_2)
    assert response_2.status_code == 200

    valid_cutoff = (base_valid.timestamp() + 1)
    valid_cutoff_iso = datetime.fromtimestamp(valid_cutoff, tz=timezone.utc).isoformat()

    valid_response = client.get(
        "/positions/ALPHA_TRADING",
        params={"valid_time": valid_cutoff_iso, "system_time": datetime.now(timezone.utc).isoformat()},
    )
    assert valid_response.status_code == 200
    valid_positions = valid_response.json()
    assert get_position_quantity(valid_positions, "AAPL", "Shares") == 17.0

    system_response = client.get(
        "/positions/ALPHA_TRADING",
        params={"valid_time": datetime.now(timezone.utc).isoformat(), "system_time": system_cutoff.isoformat()},
    )
    assert system_response.status_code == 200
    system_positions = system_response.json()
    assert get_position_quantity(system_positions, "AAPL", "Shares") == 10.0


def test_trades_by_book_supports_valid_and_system_time_asof():
    """Test point-in-time trade listing filtered by valid and system times."""
    with get_conn() as conn:
        init_db(conn)

    base_valid = datetime.now(timezone.utc)
    open_trade_1 = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 8,
        "price": 181.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": base_valid.isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    response_1 = client.post("/trades", json=open_trade_1)
    assert response_1.status_code == 200

    system_cutoff = datetime.now(timezone.utc)
    time.sleep(0.05)

    open_trade_2 = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 6,
        "price": 183.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": (base_valid.replace(microsecond=0)).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    response_2 = client.post("/trades", json=open_trade_2)
    assert response_2.status_code == 200

    valid_filtered = client.get(
        "/trades/book/ALPHA_TRADING",
        params={"valid_time": datetime.now(timezone.utc).isoformat(), "system_time": datetime.now(timezone.utc).isoformat()},
    )
    assert valid_filtered.status_code == 200
    valid_trades = valid_filtered.json()
    assert len(valid_trades) == 2

    system_filtered = client.get(
        "/trades/book/ALPHA_TRADING",
        params={"valid_time": datetime.now(timezone.utc).isoformat(), "system_time": system_cutoff.isoformat()},
    )
    assert system_filtered.status_code == 200
    system_trades = system_filtered.json()
    assert len(system_trades) == 1


def test_positions_default_now_and_future_valid_time_override():
    """Default positions should return materialized current state; explicit as-of can exclude future-effective trades."""
    with get_conn() as conn:
        init_db(conn)

    now_utc = datetime.now(timezone.utc)
    future_valid = now_utc.replace(microsecond=0).timestamp() + 3600
    future_valid_iso = datetime.fromtimestamp(future_valid, tz=timezone.utc).isoformat()

    current_trade = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 14,
        "price": 180.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": now_utc.isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }
    future_trade = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 25,
        "price": 181.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": future_valid_iso,
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    response_1 = client.post("/trades", json=current_trade)
    assert response_1.status_code == 200
    response_2 = client.post("/trades", json=future_trade)
    assert response_2.status_code == 200

    default_positions_response = client.get("/positions/ALPHA_TRADING")
    assert default_positions_response.status_code == 200
    default_positions = default_positions_response.json()
    assert get_position_quantity(default_positions, "AAPL", "Shares") == 39.0

    now_asof_response = client.get(
        "/positions/ALPHA_TRADING",
        params={"valid_time": now_utc.isoformat(), "system_time": datetime.now(timezone.utc).isoformat()},
    )
    assert now_asof_response.status_code == 200
    now_asof_positions = now_asof_response.json()
    assert get_position_quantity(now_asof_positions, "AAPL", "Shares") == 14.0

    future_positions_response = client.get(
        "/positions/ALPHA_TRADING",
        params={"valid_time": future_valid_iso, "system_time": datetime.now(timezone.utc).isoformat()},
    )
    assert future_positions_response.status_code == 200
    future_positions = future_positions_response.json()
    assert get_position_quantity(future_positions, "AAPL", "Shares") == 39.0


def test_core_reference_endpoints_return_expected_shapes():
    """Smoke-test core reference endpoints for stable response shape and seeded data."""
    with get_conn() as conn:
        init_db(conn)

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert "text/html" in root_response.headers.get("content-type", "")

    whoami_response = client.get("/whoami")
    assert whoami_response.status_code == 200
    whoami_data = whoami_response.json()
    assert "user" in whoami_data
    assert isinstance(whoami_data["user"], str)
    assert whoami_data["user"]

    books_response = client.get("/books")
    assert books_response.status_code == 200
    books = books_response.json()
    assert len(books) >= 2
    book_ids = {book["book_id"] for book in books}
    assert "ALPHA_TRADING" in book_ids
    assert "BETA_CAPITAL" in book_ids

    instruments_response = client.get("/instruments")
    assert instruments_response.status_code == 200
    instruments = instruments_response.json()
    assert len(instruments) >= 10
    aapl = next(item for item in instruments if item["instrument_key"] == "AAPL")
    assert aapl["exchange"] == "NYSE"
    assert isinstance(aapl["last_close"], float)
    assert aapl["last_close_date"]


def test_get_trade_returns_booked_event_and_empty_for_unknown_id():
    """Verify /trades/{event_id} returns the event history or empty list when unknown."""
    with get_conn() as conn:
        init_db(conn)

    trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 11,
        "price": 186.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    booked = client.post("/trades", json=trade_payload)
    assert booked.status_code == 200
    event_id = booked.json()["event_id"]

    found_response = client.get(f"/trades/{event_id}")
    assert found_response.status_code == 200
    found_events = found_response.json()
    assert len(found_events) == 1
    assert found_events[0]["event_id"] == event_id
    assert found_events[0]["type_id"] == 1

    unknown_response = client.get("/trades/00000000-0000-0000-0000-000000000000")
    assert unknown_response.status_code == 200
    assert unknown_response.json() == []


def test_positions_support_single_asof_parameter_defaults_other_to_now():
    """Ensure positions as-of logic works when only one timestamp parameter is provided."""
    with get_conn() as conn:
        init_db(conn)

    now_utc = datetime.now(timezone.utc)
    future_valid_iso = datetime.fromtimestamp(now_utc.timestamp() + 3600, tz=timezone.utc).isoformat()

    current_trade = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 9,
        "price": 180.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": now_utc.isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }
    future_trade = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 4,
        "price": 181.00,
        "currency": "USD",
        "non_economic_data": {"source": "test"},
        "valid_time": future_valid_iso,
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    assert client.post("/trades", json=current_trade).status_code == 200
    assert client.post("/trades", json=future_trade).status_code == 200

    valid_only_response = client.get(
        "/positions/ALPHA_TRADING",
        params={"valid_time": now_utc.isoformat()},
    )
    assert valid_only_response.status_code == 200
    valid_only_positions = valid_only_response.json()
    assert get_position_quantity(valid_only_positions, "AAPL", "Shares") == 9.0

    system_only_response = client.get(
        "/positions/ALPHA_TRADING",
        params={"system_time": datetime.now(timezone.utc).isoformat()},
    )
    assert system_only_response.status_code == 200
    system_only_positions = system_only_response.json()
    assert get_position_quantity(system_only_positions, "AAPL", "Shares") == 9.0


def test_valid_actions_endpoint_open_event():
    """Test valid actions endpoint returns can_cancel and can_novate for open events."""
    with get_conn() as conn:
        init_db(conn)

    # Book an open trade
    open_trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    open_response = client.post("/trades", json=open_trade_payload)
    assert open_response.status_code == 200
    event_id = open_response.json()["event_id"]

    # Get valid actions for open event
    actions_response = client.get(f"/trades/{event_id}/valid-actions")
    assert actions_response.status_code == 200
    actions = actions_response.json()
    assert actions["can_cancel"] is True
    assert actions["can_novate"] is True


def test_valid_actions_endpoint_cancelled_event():
    """Test valid actions endpoint returns cannot action for cancelled events."""
    with get_conn() as conn:
        init_db(conn)

    # Book and then cancel an open trade
    open_trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    open_response = client.post("/trades", json=open_trade_payload)
    assert open_response.status_code == 200
    event_id = open_response.json()["event_id"]

    # Cancel the trade
    cancel_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 2,
        "prior_event_id": event_id,
    }

    cancel_response = client.post("/trades", json=cancel_payload)
    assert cancel_response.status_code == 200

    # Get valid actions for cancelled event
    actions_response = client.get(f"/trades/{event_id}/valid-actions")
    assert actions_response.status_code == 200
    actions = actions_response.json()
    assert actions["can_cancel"] is False
    assert actions["can_novate"] is False


def test_valid_actions_endpoint_novated_event_locked():
    """Test that novated events are locked and cannot be cancelled or novated."""
    with get_conn() as conn:
        init_db(conn)

    # Book an open trade
    open_trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    open_response = client.post("/trades", json=open_trade_payload)
    assert open_response.status_code == 200
    event_id = open_response.json()["event_id"]

    # Novate the trade
    novate_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "GAMMA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 5,
        "prior_event_id": event_id,
    }

    novate_response = client.post("/trades", json=novate_payload)
    assert novate_response.status_code == 200

    # Get valid actions for novated event - should be locked
    actions_response = client.get(f"/trades/{event_id}/valid-actions")
    assert actions_response.status_code == 200
    actions = actions_response.json()
    assert actions["can_cancel"] is False
    assert actions["can_novate"] is False


def test_valid_actions_endpoint_novated_trade_replacement_can_act():
    """Test that the new trade created by novation can be cancelled and novated."""
    with get_conn() as conn:
        init_db(conn)

    # Book an open trade
    open_trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    open_response = client.post("/trades", json=open_trade_payload)
    assert open_response.status_code == 200
    open_event_id = open_response.json()["event_id"]

    # Novate the trade
    novate_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "GAMMA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 5,
        "prior_event_id": open_event_id,
    }

    novate_response = client.post("/trades", json=novate_payload)
    assert novate_response.status_code == 200
    novate_event_id = novate_response.json()["event_id"]

    # Get valid actions for the new trade (novation result) - should allow actions
    actions_response = client.get(f"/trades/{novate_event_id}/valid-actions")
    assert actions_response.status_code == 200
    actions = actions_response.json()
    assert actions["can_cancel"] is True
    assert actions["can_novate"] is True


def test_cancel_novated_trade_event():
    """Test that we can cancel a novation event (chain cancellation)."""
    with get_conn() as conn:
        init_db(conn)

    # Book an open trade
    open_trade_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "BETA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 1,
        "prior_event_id": None,
    }

    open_response = client.post("/trades", json=open_trade_payload)
    assert open_response.status_code == 200
    open_event_id = open_response.json()["event_id"]

    # Novate the trade
    novate_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "GAMMA_CAPITAL",
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 5,
        "prior_event_id": open_event_id,
    }

    novate_response = client.post("/trades", json=novate_payload)
    assert novate_response.status_code == 200
    novate_event_id = novate_response.json()["event_id"]

    # Now cancel the novation event (chain cancellation)
    cancel_novate_payload = {
        "book1_id": "ALPHA_TRADING",
        "book2_id": "GAMMA_CAPITAL",  # Must match novation's book2
        "book1_side": "BUY",
        "instrument_key": "AAPL",
        "quantity": 10,
        "price": 150.00,
        "currency": "USD",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "created_by": "test_user",
        "type_id": 2,
        "prior_event_id": novate_event_id,
    }

    cancel_response = client.post("/trades", json=cancel_novate_payload)
    assert cancel_response.status_code == 200
    cancel_event_id = cancel_response.json()["event_id"]

    # Verify that the cancelled novation event's valid actions are now locked
    actions_response = client.get(f"/trades/{novate_event_id}/valid-actions")
    assert actions_response.status_code == 200
    actions = actions_response.json()
    assert actions["can_cancel"] is False
    assert actions["can_novate"] is False
