import psycopg

from app_citus.config import get_database_url
from app_abstract.shared_db import get_conn_from


def get_conn(autocommit: bool = False) -> psycopg.Connection:
    return get_conn_from(get_database_url, autocommit=autocommit)


def database_exists(dbname: str) -> bool:
    """
    Check if a PostgreSQL database exists
    Returns True if the database exists, False otherwise.
    """
    with get_conn(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (dbname,))
            return cur.fetchone() is not None
        