"""OpenTelemetry setup and application metrics.

When ``APPLICATIONINSIGHTS_CONNECTION_STRING`` is present the Azure Monitor
distro is configured (traces + metrics + logs, with FastAPI/requests/psycopg
auto-instrumentation). Locally, metrics still work in-process and traces are
simply not exported — no code paths change between environments.
"""

from __future__ import annotations

from opentelemetry import metrics, trace

from oeop_core.settings import Settings

_configured = False


def setup_telemetry(service_name: str, settings: Settings) -> None:
    global _configured
    if _configured:
        return
    if settings.applicationinsights_connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=settings.applicationinsights_connection_string,
        )
    _configured = True


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


class WorkerMetrics:
    """Job-level metrics recorded by the worker."""

    def __init__(self) -> None:
        meter = metrics.get_meter("oeop.worker")
        self.job_duration = meter.create_histogram(
            "oeop.job.duration", unit="s", description="End-to-end analysis duration"
        )
        self.queue_delay = meter.create_histogram(
            "oeop.queue.delay", unit="s", description="Time between enqueue and dequeue"
        )
        self.scene_duration = meter.create_histogram(
            "oeop.scene.duration", unit="s", description="Per-scene processing duration"
        )
        self.valid_pixel_pct = meter.create_histogram(
            "oeop.scene.valid_pixel_pct", unit="%", description="Valid pixels per scene"
        )
        self.blob_upload_duration = meter.create_histogram(
            "oeop.blob.upload_duration", unit="s", description="Artifact upload duration"
        )
        self.stac_duration = meter.create_histogram(
            "oeop.stac.duration", unit="s", description="STAC search duration"
        )
        self.analyses_succeeded = meter.create_counter(
            "oeop.analyses.succeeded", description="Analyses completed successfully"
        )
        self.analyses_failed = meter.create_counter(
            "oeop.analyses.failed", description="Analyses that terminally failed"
        )
