"""Fail-closed URL admission for installed application health probes."""
import pytest
from skeleton.app.health import probe_http

@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "data:text/plain,ok", "ftp://localhost/x",
    "http://user:password@localhost:8010/health",
    "http://localhost:bad/health", "http://localhost:0/health",
    "http://localhost:8010/health#fragment", "http:///missing-host",
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
