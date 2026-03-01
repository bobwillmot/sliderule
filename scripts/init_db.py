from pathlib import Path

from app_abstract.shared_db import run_sql
from app_citus.db import get_conn, database_exists


def load_sql(path: Path) -> str:
    return path.read_text()


def init_db() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    schema_sql = load_sql(base_dir / "sql" / "schema.sql")
    seed_sql = load_sql(base_dir / "sql" / "seed_reference_data.sql")
    procs_sql = load_sql(base_dir / "sql" / "procs.sql")

        with get_conn(autocommit=True) as conn:
        if not database_exists("sliderule"):
              run_sql(conn, "CREATE DATABASE sliderule;")
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
           run_sql(conn, "CREATE USER sliderule_user WITH PASSWORD 'sliderule_passwd';")
           run_sql(conn, "GRANT ALL PRIVILEGES ON DATABASE sliderule TO sliderule_user;")

if __name__ == "__main__":
    init_db()
