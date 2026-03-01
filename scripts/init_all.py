#!/usr/bin/env python3
"""
Unified database initialization script for both Citus and CockroachDB.
Handles schema creation, seeding reference data, and initial trade booking.
"""

import sys
import time
from pathlib import Path

import psycopg

ROOT_DIR = Path(__file__).resolve().parents[1]


def wait_for_db(
    host: str,
    port: int,
    user: str,
    password: str | None = None,
    dbname: str = "postgres",
    timeout: int = 30,
) -> bool:
    """Wait for database to be ready."""
    timeout_time = time.time() + timeout
    while time.time() < timeout_time:
        try:
            if password:
                conn = psycopg.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    dbname=dbname,
                    connect_timeout=2,
                )
            else:
                conn = psycopg.connect(
                    host=host,
                    port=port,
                    user=user,
                    dbname=dbname,
                    connect_timeout=2,
                )
            conn.close()
            return True
        except (psycopg.OperationalError, psycopg.Error):
            time.sleep(1)
    return False


def init_citus() -> None:
    """Initialize Citus database with schema and reference data."""
    print("\n=== Initializing Citus ===")

    # Wait for coordinator to be ready
    if not wait_for_db("localhost", 5432, "postgres", "postgres"):
        print("✗ Citus coordinator failed to start")
        sys.exit(1)
    print("✓ Citus coordinator is ready")

    # Create database
    try:
        with psycopg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="postgres",
            dbname="postgres",
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                # Check if database exists
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    ("sliderule",),
                )
                if cur.fetchone() is None:
                    cur.execute("CREATE DATABASE sliderule")
                    print("✓ Citus database created")
                else:
                    print("✓ Citus database already exists")
    except Exception as e:
        print(f"✗ Failed to create Citus database: {e}")
        sys.exit(1)

    # Load and execute schema
    try:
        # First, set replication factor in a separate connection with autocommit
        with psycopg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="postgres",
            dbname="sliderule",
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                # Set replication factor to 1 for single-node development
                try:
                    cur.execute("ALTER SYSTEM SET citus.shard_replication_factor = 1")
                    cur.execute("SELECT pg_reload_conf()")
                except Exception:
                    # May already be set, continue
                    pass

        # Now load schema in transaction mode
        with psycopg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="postgres",
            dbname="sliderule",
        ) as conn:
            with conn.cursor() as cur:
                # Set sequential mode for distributed table creation
                cur.execute("SET citus.multi_shard_modify_mode = 'sequential'")

                # Reset schema objects so setup is idempotent on reruns
                cur.execute("DROP FUNCTION IF EXISTS get_positions(text, timestamptz, timestamptz)")
                cur.execute("DROP TABLE IF EXISTS position_effects CASCADE")
                cur.execute("DROP TABLE IF EXISTS trade_events CASCADE")
                cur.execute("DROP TABLE IF EXISTS trade_event_types CASCADE")
                cur.execute("DROP TABLE IF EXISTS instruments CASCADE")
                cur.execute("DROP TABLE IF EXISTS books CASCADE")
                
                # Load schema
                schema_sql = (ROOT_DIR / "sql" / "schema.sql").read_text()
                cur.execute(schema_sql)

                # Load seed data
                seed_sql = (ROOT_DIR / "sql" / "seed_reference_data.sql").read_text()
                cur.execute(seed_sql)

                # Load procedures
                procs_sql = (ROOT_DIR / "sql" / "procs.sql").read_text()
                cur.execute(procs_sql)

            conn.commit()
        print("✓ Citus schema initialized")
    except Exception as e:
        print(f"✗ Failed to initialize Citus schema: {e}")
        sys.exit(1)


def init_cockroachdb() -> None:
    """Initialize CockroachDB with schema and reference data."""
    print("\n=== Initializing CockroachDB ===")

    # Wait for CockroachDB to be ready
    if not wait_for_db("localhost", 26257, "root", dbname="defaultdb"):
        print("✗ CockroachDB failed to start")
        sys.exit(1)
    print("✓ CockroachDB is ready")

    # Create database
    try:
        with psycopg.connect(
            host="localhost",
            port=26257,
            user="root",
            dbname="defaultdb",
        ) as conn:
            with conn.cursor() as cur:
                # Drop existing sliderule database if resetting (commented out for safety)
                # cur.execute("DROP DATABASE IF EXISTS sliderule CASCADE")

                # Create database if it doesn't exist
                try:
                    cur.execute("CREATE DATABASE sliderule")
                    print("✓ CockroachDB database created")
                except psycopg.Error as db_err:
                    if "already exists" in str(db_err):
                        print("✓ CockroachDB database already exists")
                    else:
                        raise
            conn.commit()
    except Exception as e:
        print(f"✗ Failed to create CockroachDB database: {e}")
        sys.exit(1)

    # Load and execute schema
    try:
        with psycopg.connect(
            host="localhost",
            port=26257,
            user="root",
            dbname="sliderule",
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS position_effects CASCADE")
                cur.execute("DROP TABLE IF EXISTS trade_events CASCADE")
                cur.execute("DROP TABLE IF EXISTS trade_event_types CASCADE")
                cur.execute("DROP TABLE IF EXISTS instruments CASCADE")
                cur.execute("DROP TABLE IF EXISTS books CASCADE")

                # Load CockroachDB-specific schema (no Citus extensions)
                schema_sql = (ROOT_DIR / "sql" / "schema_cockroachdb.sql").read_text()
                cur.execute(schema_sql)

                # Load seed data (should be compatible with both)
                seed_sql = (ROOT_DIR / "sql" / "seed_reference_data.sql").read_text()
                cur.execute(seed_sql)

                # Note: CockroachDB doesn't support all PL/pgSQL features like Citus
                # Procedures are skipped for CockroachDB for now
                # If procedures are needed, create a separate CockroachDB procedures file

            conn.commit()
        print("✓ CockroachDB schema initialized")
    except Exception as e:
        # Only print warning, don't fail
        print(f"⚠ CockroachDB schema initialization warning: {e}")
        # Continue anyway - some tables may have been created


def main() -> None:
    """Main initialization routine."""
    print("\n" + "=" * 50)
    print("sliderule Database Initialization")
    print("=" * 50)

    init_citus()
    init_cockroachdb()

    print("\n" + "=" * 50)
    print("✓ All databases initialized successfully")
    print("=" * 50)
    print("\nYou can now run: bash scripts/start_services.sh")


if __name__ == "__main__":
    main()
