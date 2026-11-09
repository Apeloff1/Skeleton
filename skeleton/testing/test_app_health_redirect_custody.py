"""Transport-level regression tests for first-install health probes."""

from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from skeleton.app.health import probe_http


class HealthProbeRedirectTests(unittest.TestCase):
    def test_redirect_never_follows_target(self) -> None:
        requests: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append(self.path)
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/target")
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            blocked = probe_http("backend", origin + "/redirect", timeout=2)
            self.assertFalse(blocked.ok)
            self.assertEqual(blocked.status, 302)
            self.assertEqual(requests, ["/redirect"])
            healthy = probe_http("backend", origin + "/healthy", timeout=2)
            self.assertTrue(healthy.ok)
            self.assertEqual(healthy.status, 200)
            self.assertEqual(requests, ["/redirect", "/healthy"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_invalid_timeout_rejected_before_network(self) -> None:
        for timeout in (float("nan"), float("inf"), -1, 0, 31):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    probe_http("backend", "http://127.0.0.1:1/health", timeout=timeout)


if __name__ == "__main__":
    unittest.main()
