"""OpenTelemetry tracing. With `OTEL_EXPORTER_OTLP_ENDPOINT` set (e.g. Arize Phoenix at http://localhost:6006), every
graph step becomes a span; without it, spans are no-ops."""
from __future__ import annotations

import os
from contextlib import contextmanager

from opentelemetry import trace

_tracer = trace.get_tracer("loan_draw")
_ready = False


def setup(service: str = "loan-draw-agent") -> None:
    global _ready
    if _ready or not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _ready = True


@contextmanager
def span(name: str, **attrs):
    with _tracer.start_as_current_span(f"draw.{name}") as s:
        for k, v in attrs.items():
            s.set_attribute(k, v)
        yield s
