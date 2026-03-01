"""Shared trade service logic across database backends.

This module contains backend-agnostic query/action logic used by both the
Citus and CockroachDB trade services. Backend-specific booking persistence
remains in each backend module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from fastapi import HTTPException

from app_abstract.models import TradeEventBase, TradeRequest, ValidActionsResponse
from app_abstract.positions import (
    calculate_cancel_event_deltas,
    calculate_novation_event_deltas,
    calculate_open_event_deltas,
)


class BaseTradeService:
    """Shared trade query/action service methods.

    Subclasses provide backend-specific `book_trade()` implementation while
    reusing all read/query and lifecycle-action logic.
    """

    def __init__(
        self,
        fetch_all_fn: Callable[..., Any],
        fetch_one_fn: Callable[..., Any],
        get_conn_fn: Callable[..., Any],
        create_trade_event_fn: Callable[[dict[str, Any]], TradeEventBase],
        get_valid_actions_fn: Callable[..., ValidActionsResponse],
    ) -> None:
        self._fetch_all = fetch_all_fn
        self._fetch_one = fetch_one_fn
        self._get_conn = get_conn_fn
        self._create_trade_event = create_trade_event_fn
        self._get_valid_actions = get_valid_actions_fn

    def _row_to_trade_event(self, row: tuple) -> TradeEventBase:
        return self._create_trade_event(
            {
                "event_id": row[0],
                "book1_id": row[1],
                "book2_id": row[2],
                "book1_side": row[3],
                "instrument_key": row[4],
                "quantity": row[5],
                "price": row[6],
                "currency": row[7],
                "non_economic_data": row[8],
                "valid_time": row[9],
                "system_time": row[10],
                "created_by": row[11],
                "type_id": row[12],
                "prior_event_id": row[14],
            }
        )

    @staticmethod
    def _calculate_deltas(req: TradeRequest):
        try:
            if req.type_id == 1:
                return calculate_open_event_deltas(
                    book1_side=req.book1_side,
                    quantity=Decimal(str(req.quantity)),
                    price=Decimal(str(req.price)),
                )
            if req.type_id == 2:
                return calculate_cancel_event_deltas(
                    book1_side=req.book1_side,
                    quantity=Decimal(str(req.quantity)),
                    price=Decimal(str(req.price)),
                )
            if req.type_id == 5:
                return calculate_novation_event_deltas(
                    book1_side=req.book1_side,
                    quantity=Decimal(str(req.quantity)),
                    price=Decimal(str(req.price)),
                )
            raise HTTPException(status_code=400, detail=f"Unsupported type_id: {req.type_id}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Position delta calculation failed: {str(exc)}")

    def get_trade(self, event_id: str) -> list[TradeEventBase]:
        with self._get_conn() as conn:
            rows = self._fetch_all(
                conn,
                """
                SELECT event_id,
                       book1_id,
                       book2_id,
                       book1_side,
                       instrument_key,
                       quantity,
                       price,
                       currency,
                       non_economic_data,
                       valid_time,
                       system_time,
                       created_by,
                       type_id,
                       event_type,
                       correction_of
                FROM trade_events
                WHERE event_id = %s
                ORDER BY system_time
                """,
                (event_id,),
            )

        return [self._row_to_trade_event(row) for row in rows]

    def get_trade_valid_actions(self, event_id: str) -> ValidActionsResponse:
        with self._get_conn() as conn:
            row = self._fetch_one(
                conn,
                """
                SELECT event_id,
                       book1_id,
                       book2_id,
                       book1_side,
                       instrument_key,
                       quantity,
                       price,
                       currency,
                       non_economic_data,
                       valid_time,
                       system_time,
                       created_by,
                       type_id,
                       correction_of,
                       correction_of
                FROM trade_events
                WHERE event_id = %s
                """,
                (event_id,),
            )

            if not row:
                raise HTTPException(status_code=404, detail="Event not found")

            event = self._row_to_trade_event(row)

            has_cancel = (
                self._fetch_one(
                    conn,
                    """
                    SELECT 1
                    FROM trade_events
                    WHERE correction_of = %s::uuid
                      AND type_id = 2
                    LIMIT 1
                    """,
                    (event_id,),
                )
                is not None
            )

            has_novation = (
                self._fetch_one(
                    conn,
                    """
                    SELECT 1
                    FROM trade_events
                    WHERE correction_of = %s::uuid
                      AND type_id = 5
                    LIMIT 1
                    """,
                    (event_id,),
                )
                is not None
            )

            return self._get_valid_actions(event, has_cancel=has_cancel, has_novation=has_novation)

    def get_trades_for_book(
        self,
        book_id: str,
        valid_time: datetime | None = None,
        system_time: datetime | None = None,
    ) -> list[TradeEventBase]:
        valid_as_of = valid_time or datetime.now(timezone.utc)
        system_as_of = system_time or datetime.now(timezone.utc)

        with self._get_conn() as conn:
            rows = self._fetch_all(
                conn,
                """
                SELECT event_id,
                       book1_id,
                       book2_id,
                       book1_side,
                       instrument_key,
                       quantity,
                       price,
                       currency,
                       non_economic_data,
                       valid_time,
                       system_time,
                       created_by,
                       type_id,
                       event_type,
                       correction_of
                FROM trade_events
                WHERE (book1_id = %(book_id)s OR book2_id = %(book_id)s)
                  AND valid_time <= %(valid_as_of)s
                  AND system_time <= %(system_as_of)s
                ORDER BY valid_time DESC, system_time DESC
                """,
                {
                    "book_id": book_id,
                    "valid_as_of": valid_as_of,
                    "system_as_of": system_as_of,
                },
            )

        return [self._row_to_trade_event(row) for row in rows]

    def get_cancellable_trades_for_book(
        self,
        book_id: str,
        valid_time: datetime | None = None,
        system_time: datetime | None = None,
    ) -> list[TradeEventBase]:
        valid_as_of = valid_time or datetime.now(timezone.utc)
        system_as_of = system_time or datetime.now(timezone.utc)

        with self._get_conn() as conn:
            rows = self._fetch_all(
                conn,
                """
                SELECT event_id,
                       book1_id,
                       book2_id,
                       book1_side,
                       instrument_key,
                       quantity,
                       price,
                       currency,
                       non_economic_data,
                       valid_time,
                       system_time,
                       created_by,
                       type_id,
                       event_type,
                       correction_of
                FROM trade_events
                WHERE (book1_id = %(book_id)s OR book2_id = %(book_id)s)
                  AND valid_time <= %(valid_as_of)s
                  AND system_time <= %(system_as_of)s
                  AND type_id = 1
                ORDER BY valid_time DESC, system_time DESC
                """,
                {
                    "book_id": book_id,
                    "valid_as_of": valid_as_of,
                    "system_as_of": system_as_of,
                },
            )

        return [self._row_to_trade_event(row) for row in rows]
