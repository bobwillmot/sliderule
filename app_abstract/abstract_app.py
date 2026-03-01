"""Abstract FastAPI app composer for backend adapters.

This module provides a shared application factory to compose API routes from a
backend adapter, enabling clean separation between abstract app behavior and
backend-specific persistence/status implementations.
"""

from __future__ import annotations

import getpass
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app_abstract.models import TradeEventBase, TradeRequest, TradeResponse, ValidActionsResponse


class BackendAdapterProtocol(Protocol):
    """Protocol for backend adapters consumed by the app factory."""

    backend_id: str
    app_title: str
    startup_label: str
    trade_service: object

    def fetch_books(self) -> list[dict[str, str]]: ...

    def fetch_instruments(self) -> list[dict[str, str | float | None]]: ...

    def get_positions(
        self,
        book_id: str,
        valid_time: datetime | None = None,
        system_time: datetime | None = None,
    ) -> list[dict]: ...

    def get_position_effects(self, book_id: str | None = None, limit: int = 100) -> list[dict]: ...

    def get_cluster_status(self) -> dict: ...

    def get_shard_status(self) -> dict: ...


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"


def create_app(adapter: BackendAdapterProtocol) -> FastAPI:
    """Create a FastAPI app instance from a backend adapter."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        books = adapter.fetch_books()
        instruments = adapter.fetch_instruments()
        print(f"[{adapter.startup_label}] Loaded default books: {[book['book_id'] for book in books]}")
        print(f"[{adapter.startup_label}] Loaded instruments: {[instrument['instrument_key'] for instrument in instruments]}")
        yield

    app = FastAPI(title=adapter.app_title, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    trade_service = adapter.trade_service

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/whoami")
    def whoami():
        return {"user": getpass.getuser()}

    @app.get("/db-backend")
    def db_backend():
        return {"backend": adapter.backend_id}

    @app.get("/books")
    def list_books():
        return adapter.fetch_books()

    @app.get("/instruments")
    def list_instruments():
        return adapter.fetch_instruments()

    @app.post("/trades", response_model=TradeResponse)
    def book_trade(req: TradeRequest):
        return trade_service.book_trade(req)

    @app.get("/trades/{event_id}", response_model=list[TradeEventBase])
    def get_trade(event_id: str):
        return trade_service.get_trade(event_id)

    @app.get("/trades/{event_id}/valid-actions", response_model=ValidActionsResponse)
    def get_trade_valid_actions(event_id: str):
        return trade_service.get_trade_valid_actions(event_id)

    @app.get("/positions/{book_id}")
    def get_positions(book_id: str, valid_time: datetime | None = None, system_time: datetime | None = None):
        return adapter.get_positions(book_id, valid_time=valid_time, system_time=system_time)

    @app.get("/position-effects")
    def get_position_effects(book_id: str | None = None, limit: int = 100):
        return adapter.get_position_effects(book_id=book_id, limit=limit)

    @app.get("/trades/book/{book_id}", response_model=list[TradeEventBase])
    def get_trades_for_book(book_id: str, valid_time: datetime | None = None, system_time: datetime | None = None):
        return trade_service.get_trades_for_book(book_id, valid_time=valid_time, system_time=system_time)

    @app.get("/trades/book/{book_id}/cancellable", response_model=list[TradeEventBase])
    def get_cancellable_trades_for_book(
        book_id: str,
        valid_time: datetime | None = None,
        system_time: datetime | None = None,
    ):
        return trade_service.get_cancellable_trades_for_book(
            book_id,
            valid_time=valid_time,
            system_time=system_time,
        )

    @app.get("/status/cluster")
    def get_cluster_status():
        return adapter.get_cluster_status()

    @app.get("/status/shards")
    def get_shard_status():
        return adapter.get_shard_status()

    return app
