"""W3C trace context, bounded RED metrics and OTLP export for core.observability."""
from __future__ import annotations

import http.server
import json
import logging
import sys
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core import observability as obs  # noqa: E402

VALID = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setattr(obs, "LATENCY", obs.LatencyHistogram(window=50, max_labels=8))
    monkeypatch.setattr(obs, "ERRORS", obs.ErrorRingbuffer(size=3))
    monkeypatch.setattr(obs, "HTTP_METRICS", obs.HttpMetrics(max_series=16))
    monkeypatch.setattr(obs, "_EXPORTER", None)
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                 "OTEL_SDK_DISABLED", "OTEL_TRACES_SAMPLER_ARG"):
        monkeypatch.delenv(name, raising=False)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(obs.ObservabilityMiddleware)

    @app.get("/items/{item_id}")
    async def item(item_id: str):
        span = obs.current_span()
        return {"item": item_id, "trace_id": span.trace_id if span else None}

    @app.get("/boom")
    async def boom():
        raise HTTPException(status_code=503, detail="down")

    return app


class TestTraceparentParsing:
    def test_valid_header(self):
        assert obs.parse_traceparent(VALID) == (
            "4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7", True
        )

    @pytest.mark.parametrize("header", [
        None, "", "garbage",
        "00-00000000000000000000000000000000-00f067aa0ba902b7-01",  # zero trace id
        "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",  # zero span id
        "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",  # forbidden version
        "00-4BF92F3577B34DA6A3CE929D0E0E4736-00f067aa0ba902b7-01",  # uppercase
        VALID + "-extra",  # v00 must be exactly 55 chars
        "00-" + "a" * 600,
    ])
    def test_invalid_headers_rejected(self, header):
        assert obs.parse_traceparent(header) is None

    def test_future_version_accepted_by_prefix(self):
        header = "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00-future"
        assert obs.parse_traceparent(header) == (
            "4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7", False
        )

    def test_continues_incoming_trace_with_new_span(self):
        span = obs.start_server_span(VALID)
        assert span.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert span.parent_span_id == "00f067aa0ba902b7"
        assert span.span_id != "00f067aa0ba902b7" and len(span.span_id) == 16
        assert span.traceparent().startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")

    def test_sampler_ratio_zero_unsampled(self, monkeypatch):
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "0")
        assert obs.start_server_span(None).sampled is False


class TestMiddleware:
    def test_propagates_trace_and_uses_route_template(self):
        client = TestClient(_app())
        resp = client.get("/items/abc", headers={"traceparent": VALID})
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        parsed = obs.parse_traceparent(resp.headers["traceparent"])
        assert parsed is not None and parsed[0] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert resp.headers["server-timing"].startswith("app;dur=")
        text = obs.prom_metrics()
        assert 'route="/items/{item_id}"' in text
        assert "/items/abc" not in text

    def test_new_trace_when_header_absent_and_context_reset(self):
        client = TestClient(_app())
        resp = client.get("/items/1")
        assert len(resp.json()["trace_id"]) == 32
        assert obs.current_span() is None

    def test_unmatched_paths_do_not_grow_cardinality(self):
        client = TestClient(_app())
        for i in range(40):
            assert client.get(f"/nope/{i}").status_code == 404
        text = obs.prom_metrics()
        assert f'route="{obs.UNMATCHED_ROUTE}"' in text
        assert "/nope/" not in text
        assert len(obs.LATENCY.snapshot()) == 1

    def test_errors_total_is_monotonic_beyond_ring_size(self):
        client = TestClient(_app())
        for _ in range(5):
            assert client.get("/boom").status_code == 503
        assert obs.ERRORS.total == 5
        assert len(obs.ERRORS.snapshot()) == 3  # ring stays bounded
        assert "codedock_errors_total 5" in obs.prom_metrics()
        assert all(len(e["trace_id"]) == 32 for e in obs.ERRORS.snapshot())

    def test_histogram_is_cumulative_and_consistent(self):
        client = TestClient(_app())
        for _ in range(3):
            client.get("/items/x")
        lines = [ln for ln in obs.prom_metrics().splitlines()
                 if ln.startswith("codedock_http_request_duration_seconds_bucket")
                 and 'route="/items/{item_id}"' in ln]
        counts = [int(ln.rsplit(" ", 1)[1]) for ln in lines]
        assert counts == sorted(counts)
        assert counts[-1] == 3 and 'le="+Inf"' in lines[-1]
        assert ('codedock_http_requests_total{method="GET",route="/items/{item_id}",'
                'status_class="2xx"} 3') in obs.prom_metrics()


def test_series_cap_collapses_into_overflow():
    metrics = obs.HttpMetrics(max_series=2)
    for i in range(5):
        metrics.begin()
        metrics.observe(method="GET", route=f"/r{i}", status=200, seconds=0.01)
    text = "\n".join(metrics.exposition())
    assert obs.OVERFLOW_LABEL in text
    assert text.count("codedock_http_requests_total{") == 3


def test_log_records_carry_trace_ids():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    token = obs._CURRENT_SPAN.set(obs.start_server_span(VALID))
    try:
        assert obs.TraceContextLogFilter().filter(record)
        payload = json.loads(obs.StructuredFormatter().format(record))
    finally:
        obs._CURRENT_SPAN.reset(token)
    assert record.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert payload["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert payload["ts"].endswith("+00:00")


class _Collector(http.server.BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Collector.received.append((self.path, dict(self.headers), json.loads(body)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_otlp_export_reaches_collector(monkeypatch):
    server = http.server.HTTPServer(("127.0.0.1", 0), _Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Collector.received = []
    try:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-collector-auth=abc")
        monkeypatch.setenv("OTEL_SERVICE_NAME", "skeleton-test")
        client = TestClient(_app())
        client.get("/items/z", headers={"traceparent": VALID})
        exporter = obs.span_exporter()
        assert exporter is not None
        exporter.shutdown()
        assert exporter.stats()["exported"] == 1
        path, headers, body = _Collector.received[0]
        assert path == "/v1/traces"
        assert {k.lower(): v for k, v in headers.items()}.get("x-collector-auth") == "abc"
        rs = body["resourceSpans"][0]
        assert {"key": "service.name", "value": {"stringValue": "skeleton-test"}} in rs["resource"]["attributes"]
        span = rs["scopeSpans"][0]["spans"][0]
        assert span["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert span["parentSpanId"] == "00f067aa0ba902b7"
        assert span["name"] == "GET /items/{item_id}"
        assert span["kind"] == 2
    finally:
        server.shutdown()


def test_otlp_failures_and_overflow_never_raise():
    exporter = obs.OtlpSpanExporter("http://127.0.0.1:9/v1/traces", max_queue=1, timeout_s=0.5)
    exporter._ensure_thread = lambda: None  # keep the test deterministic
    span = obs.FinishedSpan(obs.start_server_span(VALID), "GET /x", 1, 2, {}, False)
    exporter.submit(span)
    exporter.submit(span)
    assert exporter.dropped == 1
    exporter.flush()
    assert exporter.stats()["failed_batches"] == 1


def test_disabled_sdk_or_unsampled_spans_are_not_exported(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert obs.span_exporter() is None
    exporter = obs.OtlpSpanExporter("http://127.0.0.1:9/v1/traces")
    unsampled = obs.start_server_span("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00")
    exporter.submit(obs.FinishedSpan(unsampled, "n", 1, 2, {}, False))
    assert exporter.stats()["queued"] == 0
