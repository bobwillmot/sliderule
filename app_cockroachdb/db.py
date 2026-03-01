import psycopg

from app_cockroachdb.config import get_database_url
from app_abstract.shared_db import get_conn_from


def get_conn(autocommit: bool = False) -> psycopg.Connection:
    return get_conn_from(get_database_url, autocommit=autocommit)
