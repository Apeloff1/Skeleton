"""Readiness hysteresis / fail-closed probes, bulkheads, header hygiene."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.systems.bulkhead import Bulkhead, BulkheadError, BulkheadRegistry
from skeleton.gate_plane.systems.headers import (
    CALLER_HEADER,
    is_identity_header,
    scrub_request_headers,
    scrub_response_headers,
    trusted_headers,
)
from skeleton.gate_plane.systems.readiness import (
    HiveSelfCheckProbe,
    LoopbackHttpProbe,
    ProbeResult,
    ReadinessRegistry,
    ReceiptProbe,
    is_loopback_host,
)


class Scripted:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        r = self.results.pop(0) if self.results else self.last
        self.last = r
        if isinstance(r, Exception):
            raise r
        return r


def test_unregistered_system_is_not_ready():
    reg = ReadinessRegistry(clock=ManualClock())
    s = reg.check("jeeves")
    assert not s.ready and s.reason == "no_probe_registered"


def test_optional_system_always_ready():
    reg = ReadinessRegistry(clock=ManualClock())
    reg.mark_optional("hive")
    assert reg.is_ready("hive")


def test_ttl_caches_probe():
    clock = ManualClock()
    probe = Scripted(ProbeResult.passed())
    reg = ReadinessRegistry(clock=clock, ttl_s=5.0)
    reg.register("x", probe)
    assert reg.is_ready("x") and reg.is_ready("x")
    assert probe.calls == 1
    clock.advance(5.0)
    reg.is_ready("x")
    assert probe.calls == 2


def test_probe_exception_and_bad_return_fail_closed():
    reg = ReadinessRegistry(clock=ManualClock())
    reg.register("a", Scripted(RuntimeError("boom")))
    reg.register("b", lambda: "yes")
    a = reg.check("a")
    assert not a.ready and a.reason == "probe_error"
    assert reg.check("b").reason == "probe_returned_non_result"


def test_rise_fall_hysteresis():
    clock = ManualClock()
    probe = Scripted(
        ProbeResult.passed(), ProbeResult.passed(), ProbeResult.failed("x"), ProbeResult.passed(),
        ProbeResult.failed("y"), ProbeResult.failed("z"),
    )
    reg = ReadinessRegistry(clock=clock, ttl_s=1.0, rise=2, fall=2)
    reg.register("s", probe)
    seen = []
    for _ in range(6):
        seen.append(reg.check("s").ready)
        clock.advance(1.0)
    assert seen == [False, True, True, True, True, False]


def test_expired_result_reprobes_and_failure_closes_gate():
    clock = ManualClock()
    reg = ReadinessRegistry(clock=clock, ttl_s=1.0, stale_after_s=2.0)
    reg.register("s", Scripted(ProbeResult.passed()))
    assert reg.is_ready("s")
    # After the TTL the probe reruns; a probe that now raises closes the gate.
    entry = reg._entries["s"]
    clock.advance(3.0)
    entry.checked_at = clock.monotonic() - 3.0
    entry.probe = lambda: (_ for _ in ()).throw(RuntimeError("hang"))
    assert not reg.check("s").ready


def test_registry_validation():
    with pytest.raises(ValueError):
        ReadinessRegistry(ttl_s=0)
    with pytest.raises(ValueError):
        ReadinessRegistry(rise=0)
    reg = ReadinessRegistry()
    reg.register("a", lambda: ProbeResult.passed())
    with pytest.raises(ValueError):
        reg.register("a", lambda: ProbeResult.passed())
    with pytest.raises(TypeError):
        reg.register("b", 3)


def test_hive_self_check_probe_real_and_failing():
    assert HiveSelfCheckProbe()().ok
    bad = HiveSelfCheckProbe(lambda: {"ok": 0, "failed": ["check_walk_cap:AssertionError"], "n": 5})()
    assert not bad.ok and bad.reason == "hive_checks_failed"
    assert not HiveSelfCheckProbe(lambda: None)().ok


SCHEMA = "skeleton.application.local_model_provisioning_receipt.v1"


def test_receipt_probe(tmp_path):
    p = tmp_path / "receipt.json"
    probe = ReceiptProbe(str(p), schema=SCHEMA, required_keys=["model"])
    assert probe().reason == "receipt_missing"
    p.write_text("not json")
    assert probe().reason == "receipt_not_json"
    p.write_text(json.dumps([1]))
    assert probe().reason == "receipt_not_object"
    p.write_text(json.dumps({"schema": "other"}))
    assert probe().reason == "receipt_schema_mismatch"
    p.write_text(json.dumps({"schema": SCHEMA}))
    assert probe().reason == "receipt_missing_keys"
    p.write_text(json.dumps({"schema": SCHEMA, "model": {"sha256": "ab"}}))
    assert probe().ok
    v = ReceiptProbe(str(p), validator=lambda d: None if d["model"].get("sha256") == "cd" else "sha_mismatch")
    assert v().reason == "sha_mismatch"
    big = ReceiptProbe(str(p), max_bytes=4)
    assert big().reason == "receipt_too_large"
    link = tmp_path / "link.json"
    os.symlink(p, link)
    assert ReceiptProbe(str(link))().reason == "receipt_symlink"
    assert ReceiptProbe(str(tmp_path))().reason == "receipt_not_regular"


@pytest.mark.parametrize("host, ok", [
    ("127.0.0.1", True), ("127.8.9.1", True), ("::1", True), ("[::1]", True), ("localhost", True),
    ("10.0.0.1", False), ("example.com", False), ("0.0.0.0", False), ("", False), ("localhost.evil.com", False),
])
def test_is_loopback_host(host, ok):
    assert is_loopback_host(host) is ok


class _Health(BaseHTTPRequestHandler):
    status = 200
    body = b'{"status":"ok"}'

    def do_GET(self):  # noqa: N802
        self.send_response(type(self).status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *a):
        pass


@pytest.fixture
def health_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    _Health.status, _Health.body = 200, b'{"status":"ok"}'


def test_loopback_http_probe(health_server):
    port = health_server.server_address[1]
    assert LoopbackHttpProbe("127.0.0.1", port, expect_json_key=("status", "ok"))().ok
    _Health.body = b'{"status":"loading"}'
    assert LoopbackHttpProbe("127.0.0.1", port, expect_json_key=("status", "ok"))().reason == "probe_unexpected_body"
    _Health.status = 503
    assert LoopbackHttpProbe("127.0.0.1", port)().reason == "probe_status"
    _Health.status, _Health.body = 200, b"x" * 100
    assert LoopbackHttpProbe("127.0.0.1", port, max_body_bytes=10)().reason == "probe_body_too_large"


def test_loopback_http_probe_refuses_remote_and_unreachable():
    with pytest.raises(ValueError):
        LoopbackHttpProbe("10.1.2.3", 80)
    with pytest.raises(ValueError):
        LoopbackHttpProbe("127.0.0.1", 0)
    with pytest.raises(ValueError):
        LoopbackHttpProbe("127.0.0.1", 80, path="health")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    port = srv.server_address[1]
    srv.server_close()
    assert LoopbackHttpProbe("127.0.0.1", port, timeout_s=0.5)().reason == "probe_unreachable"


def test_bulkhead_caps_and_detects_double_release():
    bh = Bulkhead("x", 2)
    a, b = bh.try_acquire(), bh.try_acquire()
    assert a and b and bh.try_acquire() is None
    bh.release(a)
    assert bh.try_acquire() is not None
    with pytest.raises(BulkheadError):
        bh.release(a)
    with pytest.raises(BulkheadError):
        Bulkhead("y", 1).release(b)
    st = bh.stats()
    assert st["rejected"] == 1 and st["peak"] == 2 and st["in_flight"] == 2
    with pytest.raises(ValueError):
        Bulkhead("z", 0)


def test_bulkhead_registry_threads():
    reg = BulkheadRegistry({"s": 5})
    got = []
    lock = threading.Lock()

    def grab():
        p = reg.get("s").try_acquire()
        with lock:
            got.append(p)

    ts = [threading.Thread(target=grab) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(1 for p in got if p is not None) == 5
    with pytest.raises(BulkheadError):
        reg.get("missing")
    with pytest.raises(ValueError):
        reg.configure("s", 1)


def test_header_scrubbing():
    raw = [
        (b"X-Principal", b"root"), (b"x-forwarded-user", b"bb"), (b"X-Skeleton-Caller", b"forged"),
        (b"x-authenticated-anything", b"1"), (b"content-type", b"application/json"), (b"x-request-id", b"r1"),
    ]
    kept, dropped = scrub_request_headers(raw)
    assert [k for k, _ in kept] == [b"content-type", b"x-request-id"]
    assert dropped == ["x-authenticated-anything", "x-forwarded-user", "x-principal", "x-skeleton-caller"]
    out, gone = scrub_response_headers([(b"x-skeleton-caller", b"svc"), (b"x-scopes", b"a"), (b"etag", b"1")])
    assert out == [(b"etag", b"1")] and gone == ["x-scopes", "x-skeleton-caller"]
    assert is_identity_header("X-Remote-User") and not is_identity_header("accept")


def test_trusted_headers_strip_control_chars():
    hdrs = dict(trusted_headers(system="jeeves", caller="svc\r\nx-evil: 1", deadline_ms=1500))
    assert hdrs[CALLER_HEADER.encode()] == b"svcx-evil: 1"
    assert hdrs[b"x-skeleton-deadline-ms"] == b"1500"
    assert dict(trusted_headers(system="hive", caller=None))[CALLER_HEADER.encode()] == b"anonymous"
