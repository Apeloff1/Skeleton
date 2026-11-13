import http.server
import threading

import pytest

from core.core_v1.transport import AllowAllPolicy, HttpTransport, PublicHttpsPolicy, RecordingTransport


def test_public_policy_rejects_private_and_http():
    p = PublicHttpsPolicy()
    for bad in ("http://example.com/x", "https://127.0.0.1/x", "https://10.0.0.1/",
                "https://user:pw@example.com/", "https://localhost/"):
        with pytest.raises(ValueError):
            p.check(bad)
    assert p.check("https://hooks.example.com/x").startswith("https://hooks.example.com")


def test_http_transport_policy_failure_is_permanent_marker():
    r = HttpTransport().post("https://127.0.0.1/x", b"{}", {}, 1)
    assert r.status_code is None and r.error.startswith("policy:")


class _Redirect(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", "http://169.254.169.254/")
        self.end_headers()

    def log_message(self, *a):
        pass


def test_http_transport_does_not_follow_redirects():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Redirect)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    class _Loopback(AllowAllPolicy):
        def check(self, url):
            return url

    r = HttpTransport(policy=_Loopback()).post(f"http://127.0.0.1:{srv.server_port}/", b"{}", {}, 5)
    srv.server_close()
    assert r.status_code == 302


def test_recording_transport():
    t = RecordingTransport()
    assert t.post("https://x", b"b", {"h": "v"}, 1).status_code == 200
    assert t.calls[0].headers == {"h": "v"}
