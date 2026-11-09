"""Regression coverage for the external HTTP reliability profile."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from skeleton.testing.http_reliability_profile import evaluate_gates, run_http_profile


class _ProfileHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A003
        del format, args

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/ok":
            self._send(200, b"ok")
            return
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Length", "3")
            self.end_headers()
            for chunk in (b"a", b"b", b"c"):
                self.wfile.write(chunk)
                self.wfile.flush()
            return
        self._send(503, b"unavailable")


@pytest.fixture
def profile_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProfileHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_profile_records_throughput_and_latency(profile_server) -> None:
    result = run_http_profile(
        f"{profile_server}/ok",
        requests=20,
        concurrency=4,
    )

    assert result.requests == 20
    assert result.concurrency == 4
    assert result.completed == 20
    assert result.failed == 0
    assert result.status_counts == {"200": 20}
    assert result.bytes_read == 40
    assert result.throughput_rps > 0
    assert result.latency.p95_ms >= 0
    assert result.ttfb.p95_ms >= 0


def test_stream_profile_counts_chunks_without_timing_thresholds(profile_server) -> None:
    result = run_http_profile(
        f"{profile_server}/stream",
        requests=5,
        concurrency=2,
        stream=True,
        chunk_size=1,
    )

    assert result.completed == 5
    assert result.failed == 0
    assert result.bytes_read == 15
    assert result.chunks == 15


def test_expected_failure_status_can_be_profiled(profile_server) -> None:
    result = run_http_profile(
        f"{profile_server}/unavailable",
        requests=4,
        concurrency=2,
        expected_statuses=(503,),
    )

    assert result.completed == 4
    assert result.failed == 0
    assert result.status_counts == {"503": 4}


def test_error_rate_gate_rejects_unexpected_status(profile_server) -> None:
    result = run_http_profile(
        f"{profile_server}/unavailable",
        requests=4,
        concurrency=2,
    )

    assert result.failed == 4
    assert result.unexpected_statuses == 4
    assert evaluate_gates(result, max_error_rate=0.0) == [
        "error_rate 1.000000 > 0.000000"
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"requests": 0}, "requests must be at least 1"),
        ({"concurrency": 0}, "concurrency must be at least 1"),
        ({"chunk_size": 0}, "chunk_size must be at least 1"),
        ({"timeout_s": 0.0}, "timeout_s must be greater than 0"),
    ],
)
def test_profile_rejects_invalid_pressure_configuration(profile_server, kwargs, message) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        run_http_profile(f"{profile_server}/ok", **kwargs)
