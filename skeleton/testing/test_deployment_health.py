"""Host health/readiness checks, runner semantics and HTTP probe interpretation."""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from collections import namedtuple

import pytest

from skeleton.deployment.health import (
    LIVE_PATH,
    READY_PATH,
    CheckKind,
    CheckRegistry,
    CheckStatus,
    HealthCheck,
    Outcome,
    build_preflight_registry,
    build_runtime_probe_registry,
    data_dir_writable_check,
    disk_space_check,
    http_probe_check,
    interpret_probe_body,
    module_check,
    port_available_check,
    python_version_check,
    sqlite_store_check,
    tcp_reachable_check,
)
from skeleton.deployment.profile import get_profile

Usage = namedtuple("Usage", "total used free")


# ------------------------------------------------------------------ runner
def test_report_rollup_is_fail_closed_on_critical_failures() -> None:
    registry = CheckRegistry()
    registry.add("ok", CheckKind.LIVENESS, lambda: Outcome.ok("fine"))
    registry.add("soft", CheckKind.READINESS, lambda: Outcome.fail("meh"), critical=False)
    report = registry.run()
    assert report.status is CheckStatus.WARN
    assert report.ok
    registry.add("hard", CheckKind.READINESS, lambda: Outcome.fail("boom"))
    report = registry.run()
    assert report.status is CheckStatus.FAIL
    assert not report.ok
    assert report.exit_code() == 1
    assert report.kind_ok(CheckKind.LIVENESS)
    assert not report.kind_ok(CheckKind.READINESS)
    assert [r.name for r in report.failures()] == ["soft", "hard"]


def test_all_pass_and_skip_roll_up_to_pass() -> None:
    registry = CheckRegistry([HealthCheck("a", CheckKind.STARTUP, lambda: Outcome.skip("n/a"))])
    registry.add("b", CheckKind.STARTUP, lambda: Outcome.ok())
    assert registry.run().status is CheckStatus.PASS


def test_crashing_and_misbehaving_checks_fail() -> None:
    registry = CheckRegistry()
    registry.add("raises", CheckKind.LIVENESS, lambda: 1 / 0)
    registry.add("wrong", CheckKind.LIVENESS, lambda: "ok")  # type: ignore[arg-type,return-value]
    results = {r.name: r for r in registry.run().results}
    assert results["raises"].status is CheckStatus.FAIL
    assert "ZeroDivisionError" in results["raises"].detail
    assert "expected Outcome" in results["wrong"].detail


def test_hung_check_times_out_without_starving_others() -> None:
    release = threading.Event()
    registry = CheckRegistry()
    registry.add("hung", CheckKind.LIVENESS, lambda: (release.wait(10), Outcome.ok())[1], timeout_s=0.2)
    registry.add("fast", CheckKind.LIVENESS, lambda: Outcome.ok("quick"))
    started = time.monotonic()
    report = registry.run()
    release.set()
    assert time.monotonic() - started < 3
    results = {r.name: r for r in report.results}
    assert results["hung"].status is CheckStatus.FAIL
    assert "timed out" in results["hung"].detail
    assert results["fast"].status is CheckStatus.PASS


def test_checks_run_concurrently() -> None:
    registry = CheckRegistry()
    for index in range(5):
        registry.add(f"s{index}", CheckKind.LIVENESS, lambda: (time.sleep(0.3), Outcome.ok())[1])
    started = time.monotonic()
    assert registry.run().ok
    assert time.monotonic() - started < 1.2


def test_registry_filters_by_kind_and_preserves_order() -> None:
    registry = CheckRegistry()
    registry.add("l", CheckKind.LIVENESS, Outcome.ok)
    registry.add("s", CheckKind.STARTUP, Outcome.ok)
    registry.add("r", CheckKind.READINESS, Outcome.ok)
    assert registry.names() == ["l", "s", "r"]
    assert [r.name for r in registry.run([CheckKind.READINESS, CheckKind.LIVENESS]).results] == ["l", "r"]
    assert registry.run([]).status is CheckStatus.PASS
    assert CheckRegistry().run().results == []


def test_registry_rejects_duplicates_and_bad_timeouts() -> None:
    registry = CheckRegistry()
    registry.add("x", CheckKind.LIVENESS, Outcome.ok)
    with pytest.raises(ValueError, match="duplicate"):
        registry.add("x", CheckKind.LIVENESS, Outcome.ok)
    with pytest.raises(ValueError, match="timeout"):
        registry.add("y", CheckKind.LIVENESS, Outcome.ok, timeout_s=0)


def test_report_dict_shape() -> None:
    registry = CheckRegistry()
    registry.add("a", CheckKind.LIVENESS, lambda: Outcome.ok("x", n=1))
    payload = registry.run().to_dict()
    assert payload["kind"] == "deployment_health"
    assert payload["summary"] == {"pass": 1, "warn": 0, "fail": 0, "skip": 0}
    assert payload["kinds"] == {"liveness": True}
    assert payload["results"][0]["data"] == {"n": 1}
    json.dumps(payload)


# --------------------------------------------------------------- factories
def test_python_version_check() -> None:
    assert python_version_check((3, 11), version=(3, 12, 1))().status is CheckStatus.PASS
    outcome = python_version_check((3, 11), version=(3, 10, 9))()
    assert outcome.status is CheckStatus.FAIL
    assert "3.10.9" in outcome.detail


def test_module_check_reports_missing_modules() -> None:
    assert module_check(["json", "os"])().status is CheckStatus.PASS
    outcome = module_check(["json", "definitely_not_a_module_xyz"])()
    assert outcome.status is CheckStatus.FAIL
    assert outcome.data["missing"] == ["definitely_not_a_module_xyz"]

    def exploding(_name):
        raise ValueError("bad spec")

    assert module_check(["x"], finder=exploding)().status is CheckStatus.FAIL


def test_data_dir_writable_check(tmp_path) -> None:
    assert data_dir_writable_check(None)().status is CheckStatus.SKIP
    assert data_dir_writable_check(tmp_path)().status is CheckStatus.PASS
    future = tmp_path / "a" / "b"
    outcome = data_dir_writable_check(future)()
    assert outcome.status is CheckStatus.PASS and outcome.data["created"] is False
    assert not future.exists()
    assert data_dir_writable_check(future, create=True)().status is CheckStatus.PASS
    assert future.is_dir()
    afile = tmp_path / "f"
    afile.write_text("x", encoding="utf-8")
    assert data_dir_writable_check(afile)().status is CheckStatus.FAIL


def test_data_dir_writable_check_fails_when_parent_not_writable(tmp_path, monkeypatch) -> None:
    import skeleton.deployment.health as health

    monkeypatch.setattr(health.os, "access", lambda *_a, **_k: False)
    assert data_dir_writable_check(tmp_path / "missing")().status is CheckStatus.FAIL


def test_disk_space_check_thresholds(tmp_path) -> None:
    assert disk_space_check(None)().status is CheckStatus.SKIP
    check = lambda free: disk_space_check(tmp_path, warn_bytes=100, fail_bytes=10,  # noqa: E731
                                          usage=lambda _p: Usage(0, 0, free))()
    assert check(5).status is CheckStatus.FAIL
    assert check(50).status is CheckStatus.WARN
    assert check(500).status is CheckStatus.PASS

    def broken(_p):
        raise OSError(5, "io error")

    assert disk_space_check(tmp_path, usage=broken)().status is CheckStatus.WARN


def test_sqlite_store_check(tmp_path) -> None:
    assert sqlite_store_check("s", ":memory:")().status is CheckStatus.SKIP
    missing = sqlite_store_check("s", str(tmp_path / "new.sqlite"))()
    assert missing.status is CheckStatus.PASS and missing.data["exists"] is False

    db = tmp_path / "real.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("create table t (x)")
    connection.commit()
    connection.close()
    good = sqlite_store_check("s", str(db))()
    assert good.status is CheckStatus.PASS and good.data["exists"] is True

    junk = tmp_path / "junk.sqlite"
    junk.write_bytes(b"this is not a database at all" * 100)
    assert sqlite_store_check("s", str(junk))().status is CheckStatus.FAIL

    assert sqlite_store_check("s", str(tmp_path))().status is CheckStatus.FAIL  # a directory


def test_sqlite_store_check_does_not_create_files(tmp_path) -> None:
    target = tmp_path / "never.sqlite"
    sqlite_store_check("s", str(target))()
    assert not target.exists()


def test_port_available_check_detects_listener() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        assert port_available_check("127.0.0.1", port)().status is CheckStatus.FAIL
    finally:
        listener.close()
    assert port_available_check("127.0.0.1", port)().status is CheckStatus.PASS


def test_tcp_reachable_check_uses_first_reachable_endpoint() -> None:
    calls = []

    class Conn:
        def close(self):
            calls.append("closed")

    def connector(address, timeout):
        calls.append(address)
        if address[0] == "down":
            raise OSError(111, "Connection refused")
        return Conn()

    outcome = tcp_reachable_check("mongo", [("down", 1), ("up", 2)], connector=connector)()
    assert outcome.status is CheckStatus.PASS
    assert outcome.data["endpoint"] == "up:2"
    assert calls == [("down", 1), ("up", 2), "closed"]
    failed = tcp_reachable_check("mongo", [("down", 1)], connector=connector)()
    assert failed.status is CheckStatus.FAIL
    assert "Connection refused" in failed.detail


def test_tcp_reachable_check_against_real_listener() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        port = listener.getsockname()[1]
        assert tcp_reachable_check("svc", [("127.0.0.1", port)])().status is CheckStatus.PASS
    finally:
        listener.close()


@pytest.mark.parametrize(
    "code,body,status",
    [
        (200, b'{"status": "up", "probes": []}', CheckStatus.PASS),
        (200, b'{"status": "down", "probes": [{"name": "db", "ok": false}]}', CheckStatus.FAIL),
        (200, b'{"status": "degraded"}', CheckStatus.WARN),
        (200, b'{"ready": false}', CheckStatus.FAIL),
        (200, b"plain text", CheckStatus.WARN),
        (200, b"", CheckStatus.PASS),
        (200, b"[1, 2]", CheckStatus.PASS),
        (503, b'{"status": "up"}', CheckStatus.FAIL),
        (404, b"", CheckStatus.FAIL),
    ],
)
def test_interpret_probe_body(code: int, body: bytes, status: CheckStatus) -> None:
    assert interpret_probe_body(code, body).status is status


def test_interpret_probe_body_lists_failing_probes() -> None:
    outcome = interpret_probe_body(200, b'{"status":"down","probes":[{"name":"db","ok":false},{"name":"x","ok":true}]}')
    assert outcome.data["failing"] == ["db"]


def test_http_probe_check_handles_transport_errors() -> None:
    def refused(_url, _timeout):
        raise OSError("connection refused")

    outcome = http_probe_check("http://127.0.0.1:1/x", fetch=refused)()
    assert outcome.status is CheckStatus.FAIL
    assert "unreachable" in outcome.detail


def test_default_fetch_refuses_non_http_urls() -> None:
    outcome = http_probe_check("file:///etc/passwd")()
    assert outcome.status is CheckStatus.FAIL
    assert "refusing" in outcome.detail


def test_runtime_probe_registry_targets_live_and_ready_paths() -> None:
    seen = []

    def fetch(url, timeout):
        seen.append(url)
        return 200, b'{"status": "up"}'

    report = build_runtime_probe_registry("http://h:1/", fetch=fetch).run()
    assert report.ok
    assert sorted(seen) == sorted(["http://h:1" + LIVE_PATH, "http://h:1" + READY_PATH])
    assert {r.kind for r in report.results} == {CheckKind.LIVENESS, CheckKind.READINESS}


# --------------------------------------------------------------- assembly
def test_preflight_registry_for_local_profile(tmp_path) -> None:
    profile = get_profile("local").with_overrides(data_dir=str(tmp_path), port=0)
    registry = build_preflight_registry(profile, include_port=False)
    names = registry.names()
    assert names[:2] == ["python", "modules"]
    assert "port" not in names
    assert {"data_dir", "disk"} <= set(names)
    assert sum(1 for n in names if n.startswith("store.")) == 8
    assert "mongo" not in names
    assert registry.run().ok


def test_preflight_registry_mongo_is_critical_only_in_production() -> None:
    def refused(*_a, **_k):
        raise OSError(111, "refused")

    dev = get_profile("test").with_overrides(mongo_uri="mongodb://db:27017")
    dev_reg = build_preflight_registry(dev, include_port=False, connector=refused)
    dev_report = dev_reg.run([CheckKind.READINESS])
    assert dev_report.ok and dev_report.status is CheckStatus.WARN

    production = get_profile("selfhost").with_overrides(mongo_uri="mongodb://db:27017", data_dir="")
    prod_report = build_preflight_registry(production, include_port=False, connector=refused).run([CheckKind.READINESS])
    assert not prod_report.ok


def test_preflight_registry_mongo_variants() -> None:
    srv = get_profile("test").with_overrides(mongo_uri="mongodb+srv://cluster.example.net")
    result = build_preflight_registry(srv, include_port=False).run([CheckKind.READINESS])
    assert next(r for r in result.results if r.name == "mongo").status is CheckStatus.SKIP
    broken = get_profile("test").with_overrides(mongo_uri="mongodb://")
    result = build_preflight_registry(broken, include_port=False).run([CheckKind.READINESS])
    assert next(r for r in result.results if r.name == "mongo").status is CheckStatus.FAIL
    no_net = build_preflight_registry(srv, include_network=False, include_port=False)
    assert "mongo" not in no_net.names()


def test_preflight_registry_adds_remote_chroma_as_non_critical() -> None:
    profile = get_profile("test").with_overrides(chroma_host="vectors.internal")

    def refused(*_a, **_k):
        raise OSError(111, "refused")

    registry = build_preflight_registry(profile, include_port=False, connector=refused)
    assert "chroma" in registry.names()
    report = registry.run([CheckKind.READINESS])
    assert report.ok
    assert not next(c for c in registry.checks() if c.name == "chroma").critical
