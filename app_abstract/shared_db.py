"""Shared database utility primitives for backend adapters."""

import logging
import time
from typing import Callable, Iterable

import psycopg
from opentelemetry import trace


DsnGetter = Callable[[], str]
_DB_LOGGER = logging.getLogger("sliderule.db")
_DB_TRACER = trace.get_tracer("sliderule.db")


def _current_ids() -> tuple[str, str]:
    span_ctx = trace.get_current_span().get_span_context()
    return (
        format(span_ctx.trace_id, "032x"),
        format(span_ctx.span_id, "016x"),
    )


def _compact_sql(statement: str, max_len: int = 180) -> str:
    normalized = " ".join(statement.split())
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[:max_len]}..."


def get_conn_from(get_database_url: DsnGetter, autocommit: bool = False) -> psycopg.Connection:
    """Create a psycopg connection using a backend-specific DSN resolver."""
    with _DB_TRACER.start_as_current_span("db.connect"):
        start = time.perf_counter()
        dsn = get_database_url()
        conn = psycopg.connect(dsn)
        conn.autocommit = autocommit
        duration_ms = (time.perf_counter() - start) * 1000
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_connect autocommit=%s duration_ms=%.2f trace_id=%s span_id=%s",
            autocommit,
            duration_ms,
            trace_id,
            span_id,
        )
        return conn


def run_sql(conn: psycopg.Connection, sql: str) -> None:
    """Execute SQL and commit when not autocommit mode."""
    statement = _compact_sql(sql)
    with _DB_TRACER.start_as_current_span("db.run_sql"):
        start = time.perf_counter()
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_run_sql_start sql=\"%s\" trace_id=%s span_id=%s",
            statement,
            trace_id,
            span_id,
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            if not conn.autocommit:
                conn.commit()
        duration_ms = (time.perf_counter() - start) * 1000
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_run_sql_end sql=\"%s\" duration_ms=%.2f trace_id=%s span_id=%s",
            statement,
            duration_ms,
            trace_id,
            span_id,
        )


def fetch_one(conn: psycopg.Connection, query: str, params: Iterable | None = None):
    """Execute a query and return the first row."""
    statement = _compact_sql(query)
    with _DB_TRACER.start_as_current_span("db.fetch_one"):
        start = time.perf_counter()
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_fetch_one_start sql=\"%s\" params_present=%s trace_id=%s span_id=%s",
            statement,
            params is not None,
            trace_id,
            span_id,
        )
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        duration_ms = (time.perf_counter() - start) * 1000
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_fetch_one_end sql=\"%s\" found=%s duration_ms=%.2f trace_id=%s span_id=%s",
            statement,
            row is not None,
            duration_ms,
            trace_id,
            span_id,
        )
        return row


def fetch_all(conn: psycopg.Connection, query: str, params: Iterable | None = None):
    """Execute a query and return all rows."""
    statement = _compact_sql(query)
    with _DB_TRACER.start_as_current_span("db.fetch_all"):
        start = time.perf_counter()
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_fetch_all_start sql=\"%s\" params_present=%s trace_id=%s span_id=%s",
            statement,
            params is not None,
            trace_id,
            span_id,
        )
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        duration_ms = (time.perf_counter() - start) * 1000
        trace_id, span_id = _current_ids()
        _DB_LOGGER.info(
            "db_fetch_all_end sql=\"%s\" rows=%s duration_ms=%.2f trace_id=%s span_id=%s",
            statement,
            len(rows),
            duration_ms,
            trace_id,
            span_id,
        )
        return rows
