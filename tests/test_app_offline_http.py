"""Black-box localhost HTTP acceptance for native offline AI.

Exercises the real Python HTTP server, native transformer, SQLite authority,
auth/origin controls, replay, branch isolation and portable recovery.
No Docker, remote provider, external model weights, browser, or mock HTTP stack.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.offline_http import (
    LocalOnlyHTTPServer, OfflineHTTPApplication,
    create_token_file,
)
from skeleton.cortex.transformer import TinyTransformer


_TOKEN = "t" * 64


class OfflineHTTPAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.model = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
            vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
            dim=8, ctx=96, seed=41, n_heads=2, n_layers=2, d_ff=16,
        )))
        self.app = OfflineHTTPApplication(
            self.model, self.folder / "http.sqlite3", token=_TOKEN
        )
        self.httpd = LocalOnlyHTTPServer(self.app)
        self.port = self.httpd.server_port
        self.worker = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        self.worker.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(timeout=4)
        self.app.close()

    def _request(self, method: str, path: str, body=None, *,
                 authorized: bool = True, headers: dict | None = None,
                 raw: bytes | None = None):
        h = dict(headers or {})
        if authorized:
            h["Authorization"] = "Bearer " + _TOKEN
        payload = raw
        if payload is None and body is not None:
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
        if payload is not None:
            h.setdefault("Content-Type", "application/json")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, body=payload, headers=h)
            response = conn.getresponse()
            status = response.status
            headers_received = dict(response.getheaders())
            raw_response = response.read()
        finally:
            conn.close()
        return status, json.loads(raw_response), headers_received

    def test_native_local_http_roundtrip_and_exactly_once_retry(self) -> None:
        status, health, _ = self._request("GET", "/v1/status")
        self.assertEqual(status, 200)
        self.assertTrue(health["local_only"])
        self.assertEqual(health["runtime_kind"], "native")
        status, item, _ = self._request(
            "POST", "/v1/sessions", {"system": "Stay factual."}
        )
        self.assertEqual(status, 201)
        sid = item["session_id"]
        endpoint = "/v1/sessions/" + sid + "/turn"
        payload = {"message": "hello", "request_id": "first-turn",
                   "max_output_tokens": 2}
        status, answer, headers = self._request("POST", endpoint, payload)
        self.assertEqual(status, 200)
        self.assertEqual(answer["revision"], 1)
        self.assertEqual(answer["output_tokens"], 2)
        self.assertEqual(len(answer["output_digest"]), 64)
        self.assertFalse(answer["replayed"])
        self.assertIn("no-store", headers["Cache-Control"])
        status, replay, _ = self._request("POST", endpoint, payload)
        self.assertEqual(status, 200)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["output_digest"], answer["output_digest"])
        self.assertEqual(replay["revision"], 1)
        status, session, _ = self._request("GET", "/v1/sessions/" + sid)
        self.assertEqual(status, 200)
        self.assertEqual(session["revision"], 1)
        self.assertEqual(
            [m["role"] for m in session["messages"]],
            ["system", "user", "assistant"],
        )
        status, conflict, _ = self._request(
            "POST", endpoint, {**payload, "message": "world"}
        )
        self.assertEqual(status, 409)
        self.assertIn("request id reused", conflict["error"])

    def test_session_listing_fork_export_import_and_deletion(self) -> None:
        status, empty, _ = self._request("GET", "/v1/sessions")
        self.assertEqual((status, empty), (200, {"sessions": []}))
        _, created, _ = self._request("POST", "/v1/sessions", {})
        sid = created["session_id"]
        _, answer, _ = self._request(
            "POST", "/v1/sessions/" + sid + "/turn",
            {"message": "hello", "request_id": "stable", "max_output_tokens": 2},
        )
        self.assertEqual(answer["revision"], 1)
        status, fork, _ = self._request(
            "POST", "/v1/sessions/" + sid + "/fork", {"after_turn": 0}
        )
        self.assertEqual(status, 201)
        new_id = fork["session_id"]
        self.assertNotEqual(new_id, sid)
        self.assertEqual(fork["revision"], 0)
        status, exported, _ = self._request(
            "GET", "/v1/sessions/" + sid + "/export"
        )
        self.assertEqual(status, 200)
        self.assertEqual(exported["body"]["revision"], 1)
        status, imported, _ = self._request(
            "POST", "/v1/sessions/import", exported
        )
        self.assertEqual(status, 201)
        import_id = imported["session_id"]
        self.assertNotIn(import_id, {sid, new_id})
        status, listing, _ = self._request("GET", "/v1/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(
            {x["session_id"]: x["revision"] for x in listing["sessions"]},
            {sid: 1, new_id: 0, import_id: 1},
        )
        status, deleted, _ = self._request(
            "DELETE", "/v1/sessions/" + sid
        )
        self.assertEqual(status, 200)
        self.assertEqual(deleted["deleted_session_id"], sid)
        status, missing, _ = self._request("GET", "/v1/sessions/" + sid)
        self.assertEqual(status, 404)
        self.assertIn("unknown", missing["error"])

    def test_loopback_access_controls_and_no_cors(self) -> None:
        status, denied, _ = self._request(
            "GET", "/v1/status", authorized=False
        )
        self.assertEqual(status, 401)
        self.assertIn("token", denied["error"])
        status, denied, _ = self._request(
            "GET", "/v1/status", headers={"Authorization": "Bearer notvalid"},
            authorized=False,
        )
        self.assertEqual(status, 401)
        status, denied, _ = self._request(
            "GET", "/v1/status",
            headers={"Origin": "https://example.net"},
        )
        self.assertEqual(status, 403)
        status, denied, _ = self._request(
            "GET", "/v1/status",
            headers={"Host": "evil.example"},
        )
        self.assertEqual(status, 403)
        status, data, headers = self._request("GET", "/v1/status")
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_malformed_json_and_oversized_requests_do_not_mutate_store(self) -> None:
        status, denied, _ = self._request(
            "POST", "/v1/sessions", raw=b'{"system":"a","system":"b"}'
        )
        self.assertEqual(status, 400)
        status, denied, _ = self._request(
            "POST", "/v1/sessions", raw=b'{"system":NaN}'
        )
        self.assertEqual(status, 400)
        status, denied, _ = self._request(
            "POST", "/v1/sessions", raw=b'{"system":1}'
        )
        self.assertEqual(status, 400)
        status, denied, _ = self._request(
            "POST", "/v1/sessions", raw=b'{' + b' ' * 66000 + b'}'
        )
        self.assertEqual(status, 413)
        status, state, _ = self._request("GET", "/v1/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(state["sessions"], [])

    def test_concurrent_same_request_id_runs_only_once(self) -> None:
        _, created, _ = self._request("POST", "/v1/sessions", {})
        sid = created["session_id"]
        request = {"message": "hello", "request_id": "parallel-one",
                   "max_output_tokens": 2}
        def call():
            return self._request(
                "POST", "/v1/sessions/" + sid + "/turn", request
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: call(), range(2)))
        self.assertEqual([x[0] for x in results], [200, 200])
        self.assertEqual(sum(x[1]["replayed"] for x in results), 1)
        self.assertEqual({x[1]["revision"] for x in results}, {1})
        _, record, _ = self._request("GET", "/v1/sessions/" + sid)
        self.assertEqual(record["revision"], 1)

    def test_static_web_ui_has_no_remote_dependencies_or_html_interpolation(self) -> None:
        for path in ("/", "/app.js", "/app.css"):
            status, data, headers = self._raw_get(path)
            self.assertEqual(status, 200)
            self.assertIn("Content-Security-Policy", headers)
            self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
            self.assertNotIn("https://", data)
        status, html, _ = self._raw_get("/")
        self.assertIn("Skeleton", html)
        status, script, _ = self._raw_get("/app.js")
        self.assertIn("textContent", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("innerHTML", script)

    def _raw_get(self, path: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8"), dict(resp.getheaders())
        finally:
            conn.close()

    def test_request_smuggling_controls_and_unsupported_methods(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.putrequest("GET", "/v1/status")
            conn.putheader("Host", "evil.example")
            conn.putheader("Authorization", "Bearer " + _TOKEN)
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn("duplicate", response.read().decode("utf-8"))
        finally:
            conn.close()
        status, error, _ = self._request(
            "GET", "/v1/status", headers={"Transfer-Encoding": "chunked"}
        )
        self.assertEqual(status, 400)
        status, error, _ = self._request("OPTIONS", "/v1/sessions")
        self.assertEqual(status, 405)
        self.assertIn("unsupported", error["error"])
        status, error, _ = self._request("GET", "/v1/status?x=1")
        self.assertEqual(status, 400)

    def test_token_file_refuses_weak_explicit_secret(self) -> None:
        from skeleton.app.offline_http import OfflineHTTPError
        path = self.folder / "weak.secret"
        with self.assertRaises(OfflineHTTPError):
            create_token_file(path, token="weak")
        self.assertFalse(path.exists())

    def test_standalone_server_deletes_only_its_own_ephemeral_token_on_exit(self):
        from skeleton.app.offline_http import main
        from unittest.mock import patch
        secret_path = self.folder / "session.secret"
        arguments = [
            "--native-checkpoint", str(self.folder / "model.json"),
            "--database", str(self.folder / "separate.sqlite3"),
            "--token-file", str(secret_path), "--port", "0",
        ]
        with (
            patch("skeleton.app.offline_http.load_native_checkpoint",
                  return_value=self.model),
            patch("skeleton.app.offline_http.LocalOnlyHTTPServer.serve_forever",
                  return_value=None),
        ):
            self.assertEqual(main(arguments), 0)
        self.assertFalse(secret_path.exists())
        secret_path.write_text("existing-operator-file", encoding="utf-8")
        with (
            patch("skeleton.app.offline_http.load_native_checkpoint",
                  return_value=self.model),
            patch("skeleton.app.offline_http.LocalOnlyHTTPServer.serve_forever",
                  return_value=None),
        ):
            self.assertEqual(main(arguments), 1)
        self.assertEqual(secret_path.read_text(encoding="utf-8"),
                         "existing-operator-file")

    def test_frozen_windowless_stdout_none_still_binds_and_cleans_up(self):
        from skeleton.app.offline_http import main
        from unittest.mock import patch
        secret_path = self.folder / "headless.secret"
        arguments = [
            "--native-checkpoint", str(self.folder / "model.json"),
            "--database", str(self.folder / "windowless.sqlite3"),
            "--token-file", str(secret_path), "--port", "0",
        ]
        with (
            patch("skeleton.app.offline_http.load_native_checkpoint",
                  return_value=self.model),
            patch("skeleton.app.offline_http.LocalOnlyHTTPServer.serve_forever",
                  return_value=None),
            patch("skeleton.app.offline_http.sys.stdout", None),
            patch("skeleton.app.offline_http.sys.stderr", None),
            patch("webbrowser.open", return_value=True) as opened,
        ):
            self.assertEqual(main(arguments), 0)
            opened.assert_called_once()
            self.assertTrue(opened.call_args.args[0].startswith(
                "http://127.0.0.1:"
            ))
        self.assertFalse(secret_path.exists())

    def test_owner_only_token_file_is_create_once(self) -> None:
        path = self.folder / "bearer.secret"
        token = create_token_file(path)
        self.assertGreaterEqual(len(token), 32)
        self.assertEqual(path.read_text().strip(), token)
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        with self.assertRaises(FileExistsError):
            create_token_file(path)


if __name__ == "__main__":
    unittest.main()
