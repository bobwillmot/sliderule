"""Citus app entrypoint composed from the abstract app factory."""

from app_abstract.abstract_app import create_app
from app_abstract.tracing import configure_tracing, instrument_fastapi_app
from app_citus.backend import CitusBackend

# Configure OpenTelemetry tracing
configure_tracing(service_name="sliderule-citus", service_version="1.0.0")

_backend = CitusBackend()
app = create_app(_backend)

# Instrument FastAPI app with OpenTelemetry
instrument_fastapi_app(app)


def fetch_books() -> list[dict[str, str]]:
    """Backward-compatible helper for direct module consumers."""
    return _backend.fetch_books()


def fetch_instruments() -> list[dict[str, str | float | None]]:
    """Backward-compatible helper for direct module consumers."""
    return _backend.fetch_instruments()
