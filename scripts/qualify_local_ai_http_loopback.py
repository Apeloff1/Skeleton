#!/usr/bin/env python3
"""Physical localhost HTTP acceptance for the protected Jeeves probe transport.

This starts ONE disposable, stdlib-only loopback HTTP server. It tests the
real urllib transport's bearer handling, no-proxy/no-redirect denial, strict
JSON parsing, bounded body, explicit single POST and canonical GET replay.
The server is NOT the Jeeves backend; all reported evidence explicitly
denies native model, persistent database and protected-chat qualification.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import sys
import threading
from typing import Any
from urllib.parse import urlsplit, parse_qs

from scripts import local_ai_chat_acceptance as chat

SCHEMA = "skeleton.local-ai.docker.physical-loopback-chat-transport.v1"


class LoopbackTransportError(RuntimeError):
    """The local HTTP transport did not enforce every required boundary."""


def exercise_loopback_http() -> dict[str, Any]:
    marker = "SKL_OFFLINE_" + secrets.token_hex(16)
    token = secrets.token_hex(32)
    calls: list[tuple[str, str]] = []
    state: dict[str, Any] = {"posted": False, "attempts": 0}
    secret_response = "Do not log application backend body"

    class Handler(BaseHTTPRequestHandler):
        server_version = "SkeletonSyntheticLocalOnly/1"
        sys_version = ""

        def log_message(self, *_args):
            # Never log the authorization header or the test challenge.
            return

        def _json(self, response: Any, status: int = 200,
                  *, content_type: str = "application/json"):
            data = json.dumps(response, sort_keys=True).encode("ascii")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            if self.headers.get("Authorization") != "Bearer " + token:
                self._json({"error": secret_response}, 401)
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path)
            calls.append(("GET", path.path))
            if not self._authorized():
                return
            if path.path == "/api/ai/providers":
                self._json({
                    "engine": "skeleton-engine", "active": "local",
                    "llm_available": True, "availability_observed": True,
                    "providers": [{
                        "id": "local", "model": "jeeves",
                        "available": True, "ownership": "engine-process",
                    }],
                })
            elif path.path == "/api/ai/chat/readiness":
                self._json({
                    "schema_version": "backend.ai.chat-readiness.v1",
                    "available": True,
                    "checks": {
                        role: {"available": True, "code": "ready"}
                        for role in ("conversation_storage", "engine", "models")
                    },
                })
            elif path.path == "/api/ai/chat/redirect":
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/leak")
                self.end_headers()
            elif path.path == "/api/ai/chat/duplicate":
                data = b'{"success":true,"success":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path.path == "/api/ai/chat/oversized":
                data = b"x" * (chat.MAX_HTTP_BYTES + 1)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path.path == "/api/ai/chat/rejected":
                self._json({"error": secret_response}, 403)
            elif path.path == "/api/ai/chat/turns/thread-001":
                query = parse_qs(path.query)
                if query.get("idempotency_key") != ["test-once"] or not state["posted"]:
                    self._json({"error": "not found"}, 404)
                    return
                self._json({
                    "success": True, "accepted": True, "terminal": True,
                    "state": "completed", "provider": "replayed",
                    "replayed": True, "ai_generated": True,
                    "engine_runtime_provider": "local",
                    "engine_execution_id": "synthetic-execution",
                    "engine_provider_receipts": ["provider:local:synthetic"],
                    "response": marker,
                })
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            path = urlsplit(self.path)
            calls.append(("POST", path.path))
            if not self._authorized():
                return
            if path.path != "/api/ai/chat":
                self._json({"error": "not found"}, 404)
                return
            state["attempts"] += 1
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("length")
                payload = json.loads(self.rfile.read(length))
                if (payload.get("thread_id") != "thread-001"
                        or payload.get("idempotency_key") != "test-once"
                        or payload.get("provider_id") != "local"
                        or payload.get("model_id") != "jeeves"
                        or payload.get("message", "").split()[-1] != marker):
                    raise ValueError("payload")
            except (TypeError, ValueError, IndexError, UnicodeError):
                self._json({"error": "invalid synthetic request"}, 400)
                return
            state["posted"] = True
            self._json({
                "success": True, "ai_generated": True,
                "provider": "skeleton-engine",
                "engine_runtime_provider": "local",
                "replayed": False, "response": marker,
                "engine_provider_receipts": ["provider:local:synthetic"],
                "engine_execution_id": "synthetic-execution",
                "engine_operation_id": "synthetic-operation",
                "turn_state": "complete",
                "assistant_message": {
                    "message_id": "synthetic-assistant", "content": marker,
                },
                "user_message": {"message_id": "synthetic-user"},
            })

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(
        target=server.serve_forever,
        name="synthetic-local-chat-http",
        daemon=True,
    )
    worker.start()
    try:
        address = "http://127.0.0.1:" + str(server.server_address[1])
        chat._admit_readiness(
            chat._http(address, token, "GET", "/api/ai/chat/readiness"),
            chat._http(address, token, "GET", "/api/ai/providers"),
        )
        original = chat._http(
            address, token, "POST", "/api/ai/chat",
            payload={
                "thread_id": "thread-001", "idempotency_key": "test-once",
                "expected_thread_version": 1, "message": "Return " + marker,
                "provider_id": "local", "model_id": "jeeves",
                "max_output_tokens": 32, "response_mode": "wait",
            },
        )
        chat._validate_original(original, marker)
        replay = chat._http(
            address, token, "GET",
            "/api/ai/chat/turns/thread-001?idempotency_key=test-once",
        )
        chat._validate_replay(original, replay, marker)
        if state["attempts"] != 1:
            raise LoopbackTransportError("chat transport unexpectedly retried POST")

        denied: dict[str, bool] = {}
        for label, path in (
            ("redirect", "/api/ai/chat/redirect"),
            ("duplicate_json", "/api/ai/chat/duplicate"),
            ("oversized_body", "/api/ai/chat/oversized"),
            ("forbidden_response", "/api/ai/chat/rejected"),
        ):
            try:
                chat._http(address, token, "GET", path)
            except chat.LocalChatProbeError as exc:
                if secret_response in str(exc) or token in str(exc):
                    raise LoopbackTransportError("HTTP exception leaked protected content")
                denied[label] = True
            else:
                raise LoopbackTransportError("synthetic hostile HTTP response admitted")
        try:
            chat._http(address, "not-the-token-but-long-enough", "GET",
                       "/api/ai/providers")
        except chat.LocalChatProbeError as exc:
            denied["unauthorized"] = True
            if token in str(exc) or secret_response in str(exc):
                raise LoopbackTransportError("unauthorized HTTP error leaked credentials")
        else:
            raise LoopbackTransportError("invalid bearer token accepted")
        if set(denied) != {
            "redirect", "duplicate_json", "oversized_body",
            "forbidden_response", "unauthorized",
        }:
            raise LoopbackTransportError("hostile HTTP cases not exhausted")
        if len([op for op, _ in calls if op == "POST"]) != 1:
            raise LoopbackTransportError("unexpected multiple chat submissions")
        return {
            "schema": SCHEMA,
            "status": "real_loopback_http_transport_exercised_not_real_jeeves",
            "actual_localhost_tcp_server_executed": True,
            "real_http_post_executed": True,
            "one_post_only": True,
            "canonical_replay_shape_checked": True,
            "redirect_denied": True,
            "duplicate_json_denied": True,
            "oversized_response_denied": True,
            "non200_denied_without_body_leak": True,
            "unauthorized_bearer_denied": True,
            "proxied_remote_provider_calls": False,
            "production_application_invoked": False,
            "real_jeeves_inference_executed": False,
            "real_user_database_mutated": False,
            "protected_chat_qualified": False,
            "release_qualified": False,
        }
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        if worker.is_alive():
            raise LoopbackTransportError("temporary loopback server did not shut down")


def main() -> int:
    try:
        print(json.dumps(exercise_loopback_http(), sort_keys=True))
        return 0
    except (chat.LocalChatProbeError, LoopbackTransportError,
            ValueError, TypeError, OSError):
        print(json.dumps({
            "schema": SCHEMA, "ok": False,
            "error": "synthetic local-only HTTP transport qualification unavailable",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
