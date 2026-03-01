"""Shared configuration helpers for backend-specific modules."""

import os


def get_database_url_from_env(env_var: str, default_url: str) -> str:
    """Resolve a database URL from environment with a backend default.

    Args:
        env_var: Environment variable name to read.
        default_url: Fallback DSN when env var is unset.

    Returns:
        Effective database URL string.
    """
    return os.getenv(env_var, default_url)
