from app_abstract.shared_config import get_database_url_from_env

# Default local connection for the Citus/Postgres dev stack.
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/sliderule"


def get_database_url() -> str:
    return get_database_url_from_env("DATABASE_URL", DEFAULT_DATABASE_URL)
