"""Headless integration of the *installed* Windows launcher browser lifecycle.

No Tk display is created. Starts a real loopback server with the canonical
native transformer and confirms its secret file and complete shutdown.
"""
from __future__ import annotations

from http.client import HTTPConnection
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.windows_launcher import WindowsLauncher
from skeleton.cortex.transformer import TinyTransformer


class OfflineWindowsBrowserLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.backend = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
            vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
            dim=8, ctx=96, seed=41, n_heads=2, n_layers=2, d_ff=16,
        )))
        # Drive exactly the production server lifecycle without allocating
        # Tk or faking HTTP sockets/SQLite.
        self.launcher = object.__new__(WindowsLauncher)
        self.launcher._browser_lock = threading.RLock()
        self.launcher._browser_server = None
        self.launcher._browser_app = None
        self.launcher._browser_worker = None
        self.launcher._browser_token_file = None
        self.launcher._launcher_closed = False
        self.addCleanup(self.launcher._stop_browser_service)

    def test_start_authenticate_generate_stop_and_delete_private_token(self):
        database = self.folder / "app.sqlite3"
        with (
            patch("skeleton.app.local_ai.load_native_checkpoint",
                  return_value=self.backend),
            patch("skeleton.app.local_ai.private_desktop_database",
                  return_value=database),
            patch("webbrowser.open", return_value=True) as browser,
        ):
            outcome = self.launcher._start_browser_service(
                self.folder / "native.json", gguf=False
            )
            self.assertIn("Offline AI browser", outcome)
            server = self.launcher._browser_server
            self.assertIsNotNone(server)
            self.assertEqual(server.server_address[0], "127.0.0.1")
            token_path = self.launcher._browser_token_file
            self.assertTrue(token_path.is_file())
            self.assertNotIn(token_path.read_text().strip(), outcome)
            if os.name != "nt":
                self.assertEqual(token_path.stat().st_mode & 0o077, 0)
            url = "http://127.0.0.1:" + str(server.server_port) + "/"
            browser.assert_called_once_with(url)
            address = server.server_port
            conn = HTTPConnection("127.0.0.1", address, timeout=10)
            try:
                conn.request("GET", "/v1/status")
                denied = conn.getresponse()
                self.assertEqual(denied.status, 401)
                denied.read()
            finally:
                conn.close()
            conn = HTTPConnection("127.0.0.1", address, timeout=10)
            try:
                conn.request("GET", "/v1/status", headers={
                    "Authorization": "Bearer " + token_path.read_text().strip(),
                })
                verified = conn.getresponse()
                self.assertEqual(verified.status, 200)
                health = json.loads(verified.read())
                self.assertEqual(health["model_digest"], self.backend.model_digest)
            finally:
                conn.close()
            self.assertIn("already running", self.launcher._start_browser_service(
                self.folder / "native.json", gguf=False
            ))
            self.assertEqual(
                self.launcher._stop_browser_service(),
                "Offline browser stopped. Ephemeral bearer-token file deleted."
            )
            self.assertFalse(token_path.exists())
            self.assertIsNone(self.launcher._browser_server)
            self.assertIsNone(self.launcher._browser_app)

    def test_launcher_closed_during_model_admission_cannot_start_server(self):
        database = self.folder / "late.sqlite3"
        def admission(_path):
            with self.launcher._browser_lock:
                self.launcher._launcher_closed = True
            return self.backend
        with (
            patch("skeleton.app.local_ai.load_native_checkpoint",
                  side_effect=admission),
            patch("skeleton.app.local_ai.private_desktop_database",
                  return_value=database),
        ):
            with self.assertRaisesRegex(RuntimeError, "closed during model admission"):
                self.launcher._start_browser_service(
                    self.folder / "native.json", gguf=False
                )
        self.assertIsNone(self.launcher._browser_server)
        self.assertEqual(list(self.folder.glob("*.secret")), [])

    def test_missing_default_webbrowser_keeps_secure_service_running(self):
        database = self.folder / "fallback.sqlite3"
        with (
            patch("skeleton.app.local_ai.load_native_checkpoint",
                  return_value=self.backend),
            patch("skeleton.app.local_ai.private_desktop_database",
                  return_value=database),
            patch("webbrowser.open", side_effect=OSError("no browser installed")),
        ):
            text = self.launcher._start_browser_service(
                self.folder / "native.json", gguf=False
            )
        self.assertIn("http://127.0.0.1:", text)
        self.assertTrue(self.launcher._browser_token_file.is_file())
        self.assertIsNotNone(self.launcher._browser_server)

    def test_server_bind_failure_does_not_leave_secret_file(self):
        # A mocked socket bind error must close the SQLite store and must
        # not create a bearer secret or silently keep a half-open service.
        database = self.folder / "app.sqlite3"
        with (
            patch("skeleton.app.local_ai.load_native_checkpoint",
                  return_value=self.backend),
            patch("skeleton.app.local_ai.private_desktop_database",
                  return_value=database),
            patch("skeleton.app.offline_http.LocalOnlyHTTPServer",
                  side_effect=OSError("port unavailable")),
        ):
            with self.assertRaisesRegex(OSError, "port unavailable"):
                self.launcher._start_browser_service(
                    self.folder / "native.json", gguf=False
                )
        self.assertIsNone(self.launcher._browser_server)
        self.assertEqual(list(self.folder.glob("*.secret")), [])


if __name__ == "__main__":
    unittest.main()
