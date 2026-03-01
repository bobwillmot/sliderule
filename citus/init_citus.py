#!/usr/bin/env python3
import psycopg
import time
import sys

def init_citus():
    # Wait for coordinator to be ready
    max_retries = 30
    for attempt in range(max_retries):
        try:
            conn = psycopg.connect("host=localhost user=postgres password=postgres dbname=postgres")
            conn.close()
            print("✓ Coordinator ready")
            break
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                print("✗ Coordinator timeout")
                sys.exit(1)

    # Create sliderule database on coordinator
    try:
        conn = psycopg.connect("host=localhost user=postgres password=postgres dbname=postgres", autocommit=True)
        try:
            conn.execute("CREATE DATABASE sliderule")
        except Exception as e:
            if "already exists" not in str(e):
                raise
        conn.close()
        print("✓ Database created on coordinator")
    except Exception as e:
        print(f"✗ Database creation failed: {e}")
        sys.exit(1)

    # Create sliderule database on workers
    for worker in ["worker1", "worker2"]:
        try:
            conn = psycopg.connect(f"host={worker} user=postgres password=postgres dbname=postgres", autocommit=True)
            try:
                conn.execute("CREATE DATABASE sliderule")
            except Exception as e:
                if "already exists" not in str(e):
                    raise
            conn.close()
            print(f"✓ Database created on {worker}")
        except Exception as e:
            print(f"✗ Database creation on {worker} failed: {e}")
            sys.exit(1)

    # Create Citus extension on coordinator and register workers
    try:
        conn = psycopg.connect("host=localhost user=postgres password=postgres dbname=sliderule")
        try:
            conn.execute("CREATE EXTENSION citus")
        except Exception as e:
            if "already exists" not in str(e):
                raise
        print("✓ Citus extension created on coordinator")
    except Exception as e:
        print(f"✗ Extension creation failed: {e}")
        sys.exit(1)

    # Create Citus extension on workers
    for worker in ["worker1", "worker2"]:
        try:
            conn = psycopg.connect(f"host={worker} user=postgres password=postgres dbname=sliderule")
            try:
                conn.execute("CREATE EXTENSION citus")
            except Exception as e:
                if "already exists" not in str(e):
                    raise
            conn.close()
            print(f"✓ Citus extension created on {worker}")
        except Exception as e:
            print(f"✗ Extension creation on {worker} failed: {e}")
            sys.exit(1)

    # Wait for workers to be ready
    time.sleep(2)

    # Register workers
    try:
        conn.execute("SELECT * FROM master_add_node('worker1', 5432)")
        conn.execute("SELECT * FROM master_add_node('worker2', 5432)")
        print("✓ Workers registered")
    except Exception as e:
        if "already exists" not in str(e):
            print(f"✗ Worker registration failed: {e}")
            sys.exit(1)
        else:
            print("✓ Workers already registered")

    conn.close()
    print("✓ Citus initialized")

if __name__ == "__main__":
    init_citus()
