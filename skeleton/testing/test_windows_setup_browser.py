"""Windows setup browser must remain usable during protected backend failure.

These tests verify only the launcher admission boundary. They do not claim
Windows, Docker, guarded inference, or real-device qualification.
"""

from __future__ import annotations

import pytest

from skeleton.app.health import ProbeResult
from skeleton.app import windows_launcher as launcher


def _probe(ok: bool, *, status: int | None = 200, detail: str = "healthy") -> ProbeResult:
    return ProbeResult(
        service="frontend", url="http://localhost:3456/", ok=ok,
        status=status, detail=detail,
    )


def test_setup_opens_when_backend_and_guard_are_unavailable(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("opening setup must not require whole-application readiness")

    monkeypatch.setattr(launcher, "runtime_status", forbidden)
    monkeypatch.setattr(
        launcher, "public_service_urls",
        lambda root, *, manifest: {"frontend": "http://localhost:3456"},
    )
    observed = []
    def probe(service, *, timeout):
        observed.append((service.name, service.public_url, service.health_path, timeout))
        return _probe(True)
    monkeypatch.setattr(launcher, "probe_local_setup", probe)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: observed.append(url) or True)

    ok, detail = launcher.open_running_application(tmp_path)
    assert ok is True
    assert observed[0] == ("frontend", "http://localhost:3456", "/setup", 2.0)
    assert observed[1] == "http://localhost:3456/setup"
    assert "NOT established" in detail


@pytest.mark.parametrize(
    ("status", "detail"),
    [(None, "URLError: health endpoint unreachable"),
     (503, "HTTP error 503"),
     (200, "health endpoint redirected")],
)
def test_setup_never_opens_browser_for_unhealthy_or_redirected_frontend(
    tmp_path, monkeypatch, status, detail,
):
    monkeypatch.setattr(launcher, "probe_local_setup", lambda *args, **kwargs: _probe(False, status=status, detail=detail))
    monkeypatch.setattr(
        launcher.webbrowser, "open",
        lambda url: pytest.fail("unhealthy frontend must never launch browser"),
    )
    ok, message = launcher.open_running_application(tmp_path)
    assert not ok
    assert "Setup UI unavailable" in message


@pytest.mark.parametrize(
    "address",
    [
        "https://outside.example:3456",
        "http://outside.example:3456",
        "http://user:pass@localhost:3456",
        "http://localhost:3456/setup?token=private",
        "http://localhost:not-a-port",
    ],
)
def test_setup_rejects_nonlocal_or_credential_bearing_browser_targets(
    tmp_path, monkeypatch, address,
):
    monkeypatch.setattr(
        launcher, "public_service_urls",
        lambda root, *, manifest: {"frontend": address},
    )
    monkeypatch.setattr(
        launcher, "probe_local_setup",
        lambda *args, **kwargs: pytest.fail("invalid target must not be probed"),
    )
    monkeypatch.setattr(
        launcher.webbrowser, "open",
        lambda url: pytest.fail("invalid target must not launch browser"),
    )
    ok, detail = launcher.open_running_application(tmp_path)
    assert not ok
    assert "private" not in detail
    assert "pass" not in detail


def test_browser_refusal_is_not_misreported_as_application_readiness(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(launcher, "probe_local_setup", lambda *args, **kwargs: _probe(True))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: False)
    ok, detail = launcher.open_running_application(tmp_path)
    assert not ok
    assert "no browser accepted" in detail


def test_browser_exception_does_not_expose_sensitive_exception_text(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "probe_local_setup", lambda *args, **kwargs: _probe(True))
    def refused(url):
        raise ValueError("private operator credential must not appear in diagnostics")
    monkeypatch.setattr(launcher.webbrowser, "open", refused)
    ok, detail = launcher.open_running_application(tmp_path)
    assert not ok
    assert "ValueError" in detail
    assert "credential" not in detail
    assert "private" not in detail


@pytest.mark.parametrize(
    ("mode", "expected_ok"),
    [
        ("setup-available-backend-offline", True),
        ("setup-missing-root-only", False),
        ("setup-redirected-to-root", False),
    ],
)
def test_real_loopback_http_setup_probe_does_not_confuse_spa_root_with_setup(
    tmp_path, monkeypatch, mode, expected_ok,
):
    """Real socket acceptance for /setup, not a mocked health verdict.

    The backend is intentionally absent. The frontend's exact route is the
    only admission condition, and a redirect to the root is never sufficient.
    This is not a Docker or Windows device qualification.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/setup":
                if mode == "setup-available-backend-offline":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    body = b"<!doctype html><html><head><title>Setup</title></head><body>setup-page</body></html>"
                elif mode == "setup-redirected-to-root":
                    self.send_response(302)
                    self.send_header("Location", "/index.html")
                    body = b""
                else:
                    self.send_response(404)
                    body = b"not-found"
            elif self.path in ("/", "/index.html"):
                self.send_response(200)
                body = b"generic-root-is-not-setup"
            else:
                self.send_response(503)
                body = b"backend-unavailable"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    opened = []
    try:
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        monkeypatch.setattr(
            launcher, "public_service_urls",
            lambda root, *, manifest: {"frontend": origin},
        )
        monkeypatch.setattr(
            launcher, "runtime_status",
            lambda *args, **kwargs: pytest.fail("backend must not gate setup"),
        )
        monkeypatch.setattr(
            launcher.webbrowser, "open",
            lambda url: opened.append(url) or True,
        )
        ok, message = launcher.open_running_application(tmp_path)
        assert ok is expected_ok
        assert opened == ([origin + "/setup"] if expected_ok else [])
        if expected_ok:
            assert "readiness are NOT established" in message
        else:
            assert "Setup UI unavailable" in message
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)



def test_setup_probe_refuses_external_redirect_without_following_it(tmp_path, monkeypatch):
    """A local /setup 302 must not send any request to its Location target."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    touched = []
    class External(BaseHTTPRequestHandler):
        def do_GET(self):
            touched.append(self.path)
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), External)
    target_worker = Thread(target=target.serve_forever, daemon=True)
    target_worker.start()

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/private")
            self.end_headers()
        def log_message(self, *args):
            pass

    source = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    source_worker = Thread(target=source.serve_forever, daemon=True)
    source_worker.start()
    try:
        origin = f"http://127.0.0.1:{source.server_address[1]}"
        monkeypatch.setattr(
            launcher, "public_service_urls",
            lambda root, *, manifest: {"frontend": origin},
        )
        monkeypatch.setattr(
            launcher.webbrowser, "open",
            lambda url: pytest.fail("redirect must not admit browser"),
        )
        ok, detail = launcher.open_running_application(tmp_path)
        assert not ok
        assert "Setup UI unavailable" in detail
        assert touched == [], "redirect target must not be contacted"
    finally:
        source.shutdown()
        source.server_close()
        source_worker.join(timeout=3)
        target.shutdown()
        target.server_close()
        target_worker.join(timeout=3)



@pytest.mark.parametrize(
    "origin",
    [
        "http://outside.example:8080",
        "https://localhost:8080",
        "http://operator:private@localhost:8080",
        "http://localhost:8080/other",
        "http://localhost:8080/?secret=1",
        "http://localhost:notaport",
    ],
)
def test_direct_setup_probe_rejects_nonlocal_or_credentialed_origin(origin):
    from dataclasses import replace
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import probe_local_setup

    frontend = replace(
        load_manifest().service("frontend"),
        public_url=origin,
        health_path="/setup",
    )
    result = probe_local_setup(frontend)
    assert not result.ok
    assert result.url == ""
    assert "private" not in repr(result)
    assert "secret" not in repr(result)


def test_setup_probe_rejects_json_200_and_empty_html_200(tmp_path, monkeypatch):
    from dataclasses import replace
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from skeleton.app.assembly import load_manifest
    from skeleton.app.health import probe_local_setup

    state = {"body": b'{"ok": true}', "type": "application/json"}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", state["type"])
            self.end_headers()
            self.wfile.write(state["body"])
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        frontend = replace(
            load_manifest().service("frontend"), public_url=origin,
            health_path="/setup",
        )
        assert not probe_local_setup(frontend).ok
        state.update(body=b"", type="text/html")
        assert not probe_local_setup(frontend).ok
        state.update(body=b"<!doctype html><html><body>Setup</body></html>", type="text/html")
        assert probe_local_setup(frontend).ok
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
