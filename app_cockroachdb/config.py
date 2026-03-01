from app_abstract.shared_config import get_database_url_from_env

# Default local connection for the CockroachDB dev stack (single-node).
# CockroachDB listens on port 26257.
DEFAULT_DATABASE_URL = "postgresql://root@localhost:26257/sliderule?sslmode=disable"


def get_database_url() -> str:
    return get_database_url_from_env("DATABASE_URL_COCKROACH", DEFAULT_DATABASE_URL)
