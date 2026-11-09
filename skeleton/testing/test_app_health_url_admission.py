"""Fail-closed URL admission for installed application health probes."""
import pytest
from skeleton.app.health import probe_http

@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "data:text/plain,ok", "ftp://localhost/x",
    "http://user:password@localhost:8010/health",
    "http://localhost:bad/health", "http://localhost:0/health",
    "http://localhost:8010/health#fragment", "http:///missing-host",
    "http://local\\host:8010/health", "http://local%68ost:8010/health",
    "http://localhost:8010/health\nX-Injected: yes",
    " http://localhost:8010/health", "http://localhost:8010/health\t",
])
def test_invalid_target_never_dispatches(monkeypatch, url):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid URL dispatched IO")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", forbidden)
    result = probe_http("engine", url)
    assert not result.ok
    assert result.status is None
    assert result.url == ""
    assert result.detail == "health probe requires HTTP(S) without credentials"

def test_valid_http_still_uses_direct_transport(monkeypatch):
    class Response:
        status = 204
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, _size):
            return b""
        def geturl(self):
            return "http://127.0.0.1:8010/health"
    seen = []
    def direct(request, *, timeout):
        seen.append((request.full_url, timeout))
        return Response()
    monkeypatch.setattr("skeleton.app.health._open_direct_health", direct)
    result = probe_http("engine", "http://127.0.0.1:8010/health", timeout=1)
    assert result.ok
    assert seen == [("http://127.0.0.1:8010/health", 1)]

@pytest.mark.parametrize("budget", [True, False, None, "3", float("nan"), float("inf"), -1, 0, 31])
def test_invalid_timeout_fails_before_io(monkeypatch, budget):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid timeout dispatched IO")
    monkeypatch.setattr("skeleton.app.health._open_direct_health", forbidden)
    with pytest.raises((ValueError, TypeError), match="timeout"):
        probe_http("engine", "http://127.0.0.1:8010/health", timeout=budget)


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:8080\nX-Injected: yes",
    "http://127.0.0.1:8080\t",
    " http://127.0.0.1:8080",
    "http://127.0.0.1:8080 ",
    "http://127.0.0.1:8080\x7f",
])
def test_setup_probe_rejects_malformed_origin_without_io(monkeypatch, origin):
    from dataclasses import replace
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import probe_local_setup

    service = replace(load_manifest().service("frontend"), public_url=origin, health_path="/setup")
    def forbidden(*args, **kwargs):
        pytest.fail("malformed setup origin dispatched IO")
    monkeypatch.setattr("skeleton.app.health.build_opener", forbidden)
    result = probe_local_setup(service)
    assert not result.ok
    assert result.status is None
    assert result.url == ""


@pytest.mark.parametrize("budget", [True, False, None, "3", float("nan"), float("inf"), 0, -1, 11])
def test_setup_probe_rejects_invalid_timeout_before_io(monkeypatch, budget):
    from dataclasses import replace
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import probe_local_setup

    service = replace(load_manifest().service("frontend"), public_url="http://127.0.0.1:8080", health_path="/setup")
    def forbidden(*args, **kwargs):
        pytest.fail("invalid setup timeout dispatched IO")
    monkeypatch.setattr("skeleton.app.health.build_opener", forbidden)
    with pytest.raises(ValueError, match="timeout"):
        probe_local_setup(service, timeout=budget)


@pytest.mark.parametrize("field,value", [
    ("timeout", True), ("timeout", None), ("timeout", "3"),
    ("timeout", float("nan")), ("timeout", float("inf")),
    ("delay", False), ("delay", None), ("delay", "1"),
    ("delay", float("nan")), ("delay", float("-inf")),
])
def test_wait_budget_validation_precedes_probe(monkeypatch, field, value):
    from skeleton.app.health import wait_for_application
    def forbidden(*args, **kwargs):
        pytest.fail("invalid wait budget dispatched IO")
    monkeypatch.setattr("skeleton.app.health.probe_application", forbidden)
    with pytest.raises(ValueError, match=field):
        wait_for_application(**{field: value})
