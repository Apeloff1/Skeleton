"""Regression: authenticated studio probes must not inherit HTTP proxy routing."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from skeleton.app.studio_readiness import _server_snapshot


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append((self.path, self.headers.get("Authorization")))
        body = json.dumps({"schema_version": "skeleton.game.studio_readiness.v1"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class DoctorProxyIsolationTests(unittest.TestCase):
    def test_authenticated_loopback_probe_ignores_inherited_proxy(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.requests = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
                "NO_PROXY": "",
                "no_proxy": "",
            }):
                result = _server_snapshot(
                    f"http://127.0.0.1:{server.server_port}",
                    "operator-private-token", 2.0,
                )
            self.assertTrue(result["observed"])
            self.assertEqual(server.requests, [
                ("/api/game-studio-health", "Bearer operator-private-token")
            ])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_remote_plaintext_rejects_authentication(self):
        with self.assertRaisesRegex(ValueError, "HTTPS or loopback"):
            _server_snapshot("http://192.0.2.1:8080", "operator-private-token", 1.0)

    def test_url_credentials_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS or loopback"):
            _server_snapshot("http://user:password@localhost:8080", "operator-private-token", 1.0)


if __name__ == "__main__":
    unittest.main()
