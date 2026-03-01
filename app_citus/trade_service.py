"""Citus trade service with shared query logic and Citus-specific booking."""

import getpass

from fastapi import HTTPException
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from psycopg.types.json import Json

from app_abstract.models import TradeRequest, TradeResponse, create_trade_event, get_valid_actions
from app_abstract.shared_trade_service import BaseTradeService
from app_abstract.shared_db import fetch_all, fetch_one
from app_citus.db import get_conn

tracer = trace.get_tracer(__name__)


class TradeService(BaseTradeService):
    """Trade service for Citus backend.

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
                "app.backend": "citus",
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
                    fetch_one(conn, "SELECT create_book(%s::text)", (req.book1_id,))
                    fetch_one(conn, "SELECT create_book(%s::text)", (req.book2_id,))
                    fetch_one(
                        conn,
                        "SELECT create_instrument(%s::text, %s::text)",
                        (req.instrument_key, req.instrument_key),
                    )

                    if req.type_id == 2:
                        if req.prior_event_id is None:
                            raise HTTPException(status_code=400, detail="CancelEvent requires prior_event_id")
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

                    if req.type_id == 5:
                        if req.prior_event_id is None:
                            raise HTTPException(status_code=400, detail="NovationEvent requires prior_event_id")
                        prior_event = fetch_one(
                            conn,
                            """
                            SELECT book2_id
                            FROM trade_events
                            WHERE event_id = %s::uuid
                            """,
                            (req.prior_event_id,),
                        )
                        if not prior_event:
                            raise HTTPException(status_code=400, detail="Prior event not found")
                        prior_book2_id = prior_event[0]
                        if req.book2_id == prior_book2_id:
                            raise HTTPException(
                                status_code=400,
                                detail="NovationEvent: new book2_id cannot be the same as prior book2_id",
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
                            req.book1_id,
                            req.book2_id,
                            req.book1_side,
                            req.instrument_key,
                            req.quantity,
                            req.price,
                            req.currency,
                            Json(req.non_economic_data) if req.non_economic_data is not None else None,
                            req.valid_time,
                            created_by,
                            req.type_id,
                            req.prior_event_id,
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

                if not row:
                    raise HTTPException(status_code=500, detail="Trade booking failed")

                event_id = row[0]
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
