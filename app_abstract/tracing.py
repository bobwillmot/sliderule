"""OpenTelemetry observability configuration for sliderule.

This module initializes tracing, metrics, and optional OTLP log export with
auto-instrumentation for FastAPI and psycopg.
"""

import logging
import os
import socket
import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import start_http_server

_REQUEST_COUNTER = None
_REQUEST_DURATION_HISTOGRAM = None
_METRICS_ENABLED = False
_LOGS_ENABLED = False
_REQUEST_LOGGER = logging.getLogger("sliderule.http")


def _default_metrics_port(service_name: str) -> int:
    if service_name == "sliderule-citus":
        return 9464
    if service_name == "sliderule-cockroachdb":
        return 9465
    return 9466


def configure_metrics(service_name: str, service_version: str = "1.0.0") -> None:
    """Configure Prometheus-exported OpenTelemetry metrics.

    Args:
        service_name: Name of the service (e.g., "sliderule-citus")
        service_version: Version of the service
    """
    global _REQUEST_COUNTER, _REQUEST_DURATION_HISTOGRAM, _METRICS_ENABLED

    if _METRICS_ENABLED:
        return

    metric_reader = PrometheusMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter("sliderule.http", service_version)

    _REQUEST_COUNTER = meter.create_counter(
        "sliderule_http_server_requests_total",
        unit="1",
        description="Total number of HTTP requests handled by sliderule",
    )
    _REQUEST_DURATION_HISTOGRAM = meter.create_histogram(
        "sliderule_http_server_duration_ms",
        unit="ms",
        description="HTTP request duration in milliseconds",
    )

    metrics_port = int(os.getenv("OTEL_METRICS_PORT", str(_default_metrics_port(service_name))))
    metrics_host = os.getenv("OTEL_METRICS_HOST", "0.0.0.0")
    
    try:
        start_http_server(port=metrics_port, addr=metrics_host)
        _METRICS_ENABLED = True
        print(f"[OpenTelemetry] Metrics configured for {service_name}")
        print(f"[OpenTelemetry] Exposing Prometheus metrics at http://{metrics_host}:{metrics_port}/metrics")
    except OSError as e:
        if e.errno in (48, 98):  # Address already in use (macOS/Linux)
            print(f"[OpenTelemetry] Metrics server already running on port {metrics_port}, skipping startup")
            _METRICS_ENABLED = True
        else:
            raise


def configure_logs(resource: Resource, service_name: str) -> None:
    """Configure optional OTLP log export with OpenTelemetry.

    Args:
        resource: OpenTelemetry Resource containing service metadata
        service_name: Name of the service (e.g., "sliderule-citus")
    """
    global _LOGS_ENABLED

    if _LOGS_ENABLED:
        return

    logs_enabled = os.getenv("OTEL_LOGS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not logs_enabled:
        print(f"[OpenTelemetry] OTLP log export disabled for {service_name} (set OTEL_LOGS_ENABLED=false to keep disabled)")
        return

    logs_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        os.getenv("OTEL_EXPORTER_TEMPO_ENDPOINT", "http://localhost:4319"),
    )
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=logs_endpoint, insecure=True)
        )
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(os.getenv("OTEL_APP_LOG_LEVEL", "INFO").upper())

    if not any(isinstance(h, LoggingHandler) for h in root_logger.handlers):
        root_logger.addHandler(LoggingHandler(level=root_logger.level, logger_provider=logger_provider))

    _LOGS_ENABLED = True
    print(f"[OpenTelemetry] OTLP log export enabled for {service_name}")
    print(f"[OpenTelemetry] Sending logs to: {logs_endpoint}")


def configure_tracing(service_name: str, service_version: str = "1.0.0") -> None:
    """Configure OpenTelemetry tracing and metrics export.

    Args:
        service_name: Name of the service (e.g., "sliderule-citus", "sliderule-cockroachdb")
        service_version: Version of the service
    """
    deployment_environment = os.getenv("OTEL_DEPLOYMENT_ENV", "development")

    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "service.namespace": "sliderule",
            "deployment.environment": deployment_environment,
            "host.name": socket.gethostname(),
        }
    )

    # Initialize tracer provider
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    # Configure OTLP exporter to Tempo
    tempo_endpoint = os.getenv("OTEL_EXPORTER_TEMPO_ENDPOINT", "http://localhost:4317")
    tempo_exporter = OTLPSpanExporter(
        endpoint=tempo_endpoint,
        insecure=True,
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(tempo_exporter))

    # Auto-instrument psycopg for database tracing
    PsycopgInstrumentor().instrument()

    # Configure Prometheus-exported OpenTelemetry metrics
    configure_metrics(service_name=service_name, service_version=service_version)

    # Configure optional OTLP log export
    configure_logs(resource=resource, service_name=service_name)

    print(f"[OpenTelemetry] Tracing configured for {service_name}")
    print(f"[OpenTelemetry] Sending traces to Tempo: {tempo_endpoint}")
    print(f"[OpenTelemetry] View traces via Grafana at http://localhost:3000")


def instrument_fastapi_app(app) -> None:
    """Instrument a FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(app)

    if getattr(app.state, "otel_metrics_middleware_installed", False):
        return

    @app.middleware("http")
    async def otel_http_metrics_middleware(request, call_next):
        start = time.perf_counter()
        status_code = 500
        duration_ms = 0.0

        route = request.url.path
        route_template = request.scope.get("route")
        if route_template is not None and hasattr(route_template, "path"):
            route = route_template.path

        span_ctx = trace.get_current_span().get_span_context()
        trace_id = format(span_ctx.trace_id, "032x")
        span_id = format(span_ctx.span_id, "016x")
        _REQUEST_LOGGER.info(
            "http_request_start method=%s route=%s client=%s trace_id=%s span_id=%s",
            request.method,
            route,
            request.client.host if request.client else "unknown",
            trace_id,
            span_id,
        )

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            span_ctx = trace.get_current_span().get_span_context()
            _REQUEST_LOGGER.exception(
                "http_request_error method=%s route=%s error=%s trace_id=%s span_id=%s",
                request.method,
                route,
                type(exc).__name__,
                format(span_ctx.trace_id, "032x"),
                format(span_ctx.span_id, "016x"),
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            if _REQUEST_COUNTER is None or _REQUEST_DURATION_HISTOGRAM is None:
                return

            attributes = {
                "http.method": request.method,
                "http.route": route,
                "http.status_code": status_code,
            }
            _REQUEST_COUNTER.add(1, attributes=attributes)
            _REQUEST_DURATION_HISTOGRAM.record(
                duration_ms,
                attributes=attributes,
            )
            span_ctx = trace.get_current_span().get_span_context()
            _REQUEST_LOGGER.info(
                "http_request_end method=%s route=%s status=%s duration_ms=%.2f trace_id=%s span_id=%s",
                request.method,
                route,
                status_code,
                duration_ms,
                format(span_ctx.trace_id, "032x"),
                format(span_ctx.span_id, "016x"),
            )

    app.state.otel_metrics_middleware_installed = True
