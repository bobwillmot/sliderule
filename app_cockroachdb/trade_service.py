"""Cockroach trade service with shared query logic and Cockroach booking."""

import getpass
from decimal import Decimal

from fastapi import HTTPException
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from psycopg.types.json import Json

from app_abstract.shared_trade_service import BaseTradeService
from app_abstract.shared_db import fetch_all, fetch_one
from app_cockroachdb.db import get_conn
from app_cockroachdb.models import TradeRequest, TradeResponse, create_trade_event, get_valid_actions

tracer = trace.get_tracer(__name__)


class TradeService(BaseTradeService):
    """Trade service for Cockroach backend.

    Shared query/action methods are inherited from `BaseTradeService`.
    """

    def __init__(self) -> None:
        super().__init__(
            fetch_all_fn=fetch_all,
            fetch_one_fn=fetch_one,
            get_conn_fn=get_conn,
            create_trade_event_fn=create_trade_event,
            get_valid_actions_fn=get_valid_actions,
        )

    def book_trade(self, req: TradeRequest) -> TradeResponse:
        """Book a trade lifecycle event.

        Args:
            req: Trade request containing lifecycle event fields.

        Returns:
            TradeResponse containing booked event ID.

        Raises:
            HTTPException: For validation failures or booking errors.

        References:
            See docs/trade_events.rst for event type definitions and booking rules.
        """
        with tracer.start_as_current_span(
            "sliderule.trades.book",
            attributes={
                "db.system": "postgresql",
                "db.namespace": "sliderule",
                "app.backend": "cockroachdb",
                "trade.event_type": req.type_id,
                "trade.book1_id": req.book1_id,
                "trade.book2_id": req.book2_id,
                "trade.instrument_key": req.instrument_key,
                "trade.quantity": float(req.quantity),
                "trade.price": float(req.price),
                "trade.currency": req.currency,
                "trade.has_prior_event": req.prior_event_id is not None,
                "cqrs.side": "command",
                "bitemporal.valid_time": req.valid_time.isoformat(),
            },
        ) as span:
            try:
                created_by = getpass.getuser()
                span.set_attribute("trade.created_by", created_by)
                if req.prior_event_id is not None:
                    span.set_attribute("trade.prior_event_id", str(req.prior_event_id))
                deltas = self._calculate_deltas(req)

                with get_conn() as conn:
                    fetch_one(
                        conn,
                        """
                        INSERT INTO books (book_id, book_name)
                        VALUES (%s, %s)
                        ON CONFLICT (book_id) DO NOTHING
                        RETURNING book_id
                        """,
                        (req.book1_id, req.book1_id),
                    )
                    fetch_one(
                        conn,
                        """
                        INSERT INTO books (book_id, book_name)
                        VALUES (%s, %s)
                        ON CONFLICT (book_id) DO NOTHING
                        RETURNING book_id
                        """,
                        (req.book2_id, req.book2_id),
                    )
                    fetch_one(
                        conn,
                        """
                        INSERT INTO instruments (instrument_key, description)
                        VALUES (%s, %s)
                        ON CONFLICT (instrument_key) DO NOTHING
                        RETURNING instrument_key
                        """,
                        (req.instrument_key, req.instrument_key),
                    )

                    effective_book1_id = req.book1_id
                    effective_book2_id = req.book2_id
                    effective_book1_side = req.book1_side
                    effective_instrument_key = req.instrument_key
                    effective_quantity = req.quantity
                    effective_price = req.price
                    effective_currency = req.currency
                    effective_non_economic_data = req.non_economic_data

                    if req.type_id == 2:
                        if req.prior_event_id is None:
                            raise HTTPException(status_code=400, detail="CancelEvent requires prior_event_id")
                        prior_event = fetch_one(
                            conn,
                            """
                            SELECT book1_id,
                                   book2_id,
                                   book1_side,
                                   instrument_key,
                                   quantity,
                                   price,
                                   currency,
                                   non_economic_data
                            FROM trade_events
                            WHERE event_id = %s::uuid
                            """,
                            (req.prior_event_id,),
                        )
                        if not prior_event:
                            raise HTTPException(status_code=400, detail="Prior event not found")
                        already_cancelled = fetch_one(
                            conn,
                            """
                            SELECT 1
                            FROM trade_events
                            WHERE correction_of = %s::uuid
                              AND type_id = 2
                            LIMIT 1
                            """,
                            (req.prior_event_id,),
                        )
                        if already_cancelled:
                            raise HTTPException(status_code=400, detail="Trade already cancelled")

                        effective_book1_id = prior_event[0]
                        effective_book2_id = prior_event[1]
                        effective_book1_side = prior_event[2]
                        effective_instrument_key = prior_event[3]
                        effective_quantity = float(prior_event[4])
                        effective_price = float(prior_event[5])
                        effective_currency = prior_event[6]
                        effective_non_economic_data = prior_event[7]

                        deltas = self._calculate_deltas(
                            TradeRequest(
                                book1_id=effective_book1_id,
                                book2_id=effective_book2_id,
                                book1_side=effective_book1_side,
                                instrument_key=effective_instrument_key,
                                quantity=effective_quantity,
                                price=effective_price,
                                currency=effective_currency,
                                non_economic_data=effective_non_economic_data,
                                valid_time=req.valid_time,
                                created_by=created_by,
                                type_id=2,
                                prior_event_id=req.prior_event_id,
                            )
                        )

                    if req.type_id == 5:
                        if req.prior_event_id is None:
                            raise HTTPException(status_code=400, detail="NovationEvent requires prior_event_id")
                        prior_event = fetch_one(
                            conn,
                            """
                            SELECT book1_id,
                                   book2_id,
                                   book1_side,
                                   instrument_key,
                                   quantity,
                                   price,
                                   currency,
                                   non_economic_data
                            FROM trade_events
                            WHERE event_id = %s::uuid
                            """,
                            (req.prior_event_id,),
                        )
                        if not prior_event:
                            raise HTTPException(status_code=400, detail="Prior event not found")
                        prior_book2_id = prior_event[1]
                        if req.book2_id == prior_book2_id:
                            raise HTTPException(
                                status_code=400,
                                detail="NovationEvent: new book2_id cannot be the same as prior book2_id",
                            )

                        effective_book1_id = prior_event[0]
                        effective_book2_id = req.book2_id
                        effective_book1_side = prior_event[2]
                        effective_instrument_key = prior_event[3]
                        effective_quantity = float(prior_event[4])
                        effective_price = float(prior_event[5])
                        effective_currency = prior_event[6]
                        effective_non_economic_data = prior_event[7]

                        deltas = self._calculate_deltas(
                            TradeRequest(
                                book1_id=effective_book1_id,
                                book2_id=effective_book2_id,
                                book1_side=effective_book1_side,
                                instrument_key=effective_instrument_key,
                                quantity=effective_quantity,
                                price=effective_price,
                                currency=effective_currency,
                                non_economic_data=effective_non_economic_data,
                                valid_time=req.valid_time,
                                created_by=created_by,
                                type_id=5,
                                prior_event_id=req.prior_event_id,
                            )
                        )

                    row = fetch_one(
                        conn,
                        """
                        INSERT INTO trade_events (
                            book1_id,
                            book2_id,
                            book1_side,
                            instrument_key,
                            quantity,
                            price,
                            currency,
                            non_economic_data,
                            valid_time,
                            created_by,
                            type_id,
                            correction_of
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s::jsonb,
                            %s,
                            %s,
                            %s,
                            %s
                        )
                        RETURNING event_id
                        """,
                        (
                            effective_book1_id,
                            effective_book2_id,
                            effective_book1_side,
                            effective_instrument_key,
                            effective_quantity,
                            effective_price,
                            effective_currency,
                            Json(effective_non_economic_data) if effective_non_economic_data is not None else Json({}),
                            req.valid_time,
                            created_by,
                            req.type_id,
                            req.prior_event_id,
                        ),
                    )

                    if not row:
                        raise HTTPException(status_code=500, detail="Trade booking failed")

                    event_id = row[0]

                    position_effect_rows: list[tuple[str, str, str, Decimal]] = []

                    if deltas.apply_book1:
                        position_effect_rows.append((effective_book1_id, effective_instrument_key, "Shares", deltas.book1_shares_delta))
                        position_effect_rows.append((effective_book1_id, effective_instrument_key, "Proceeds", deltas.book1_proceeds_delta))

                    if deltas.apply_book2:
                        position_effect_rows.append((effective_book2_id, effective_instrument_key, "Shares", deltas.book2_shares_delta))
                        position_effect_rows.append((effective_book2_id, effective_instrument_key, "Proceeds", deltas.book2_proceeds_delta))

                    if req.type_id == 5 and req.prior_event_id is not None:
                        prior_book2 = fetch_one(
                            conn,
                            "SELECT book2_id FROM trade_events WHERE event_id = %s::uuid",
                            (req.prior_event_id,),
                        )
                        if prior_book2:
                            old_book2_id = prior_book2[0]
                            position_effect_rows.append((old_book2_id, effective_instrument_key, "Shares", deltas.old_book2_shares_delta))
                            position_effect_rows.append((old_book2_id, effective_instrument_key, "Proceeds", deltas.old_book2_proceeds_delta))
                            position_effect_rows.append((effective_book2_id, effective_instrument_key, "Shares", -deltas.old_book2_shares_delta))
                            position_effect_rows.append((effective_book2_id, effective_instrument_key, "Proceeds", -deltas.old_book2_proceeds_delta))

                    for book_id, instrument_key, position_type, quantity in position_effect_rows:
                        fetch_one(
                            conn,
                            """
                            INSERT INTO position_effects (
                                event_book1_id,
                                event_id,
                                book_id,
                                instrument_key,
                                position_type,
                                quantity
                            )
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING event_id
                            """,
                            (
                                effective_book1_id,
                                event_id,
                                book_id,
                                instrument_key,
                                position_type,
                                quantity,
                            ),
                        )

                    conn.commit()

                    span.set_attribute("trade.event_id", str(event_id))
                    span.set_status(Status(StatusCode.OK))
                    return TradeResponse(event_id=event_id)

            except HTTPException as exc:
                span.set_attribute("error.type", "HTTPException")
                span.set_attribute("error.message", str(exc.detail))
                span.set_status(Status(StatusCode.ERROR, str(exc.detail)))
                raise
            except Exception as e:
                span.record_exception(e)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise
