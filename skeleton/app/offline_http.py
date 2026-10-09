"""Authenticated loopback-only HTTP access to Skeleton's offline model and chat.

No framework dependency, external service, remote bind, hosted model transport,
cookies or credentials from browser storage. All model work uses the same
canonical NativeRuntimeLocalModel or digest-pinned llama.cpp execution path
as the installed desktop application.
"""
from __future__ import annotations

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from typing import Any
from urllib.parse import urlsplit

from skeleton.ai.model_runtime.offline_chat import (
    MAX_BUNDLE_BYTES, OfflineChatStore, _digest_request, _identifier,
    _strict_pairs, _reject_constant,
)
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError
from skeleton.app.local_ai import (
    DurableOfflineAISession, LocalDesktopModel, OfflineAIError,
    _model_tokenizer_digest, load_gguf_deployment, load_native_checkpoint,
    private_desktop_database,
)
from skeleton.app.offline_web import HTML, CSS, JAVASCRIPT


MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CHAT_REQUEST_BYTES = 64 * 1024
MAX_CONNECTIONS = 16


class OfflineHTTPError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8", errors="strict"),
                          object_pairs_hook=_strict_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, ValueError) as exc:
        raise OfflineHTTPError(400, "invalid JSON request") from exc
    if not isinstance(data, dict):
        raise OfflineHTTPError(400, "JSON request must be an object")
    return data


def _fields(body: dict[str, Any], allowed: set[str], required: set[str]) -> None:
    if set(body) - allowed or not required.issubset(body):
        raise OfflineHTTPError(400, "unexpected or missing request fields")


def _budget(body: dict[str, Any], default: int) -> int:
    value = body.get("max_output_tokens", default)
    if type(value) is not int or not 1 <= value <= 8192:
        raise OfflineHTTPError(400, "invalid model output token budget")
    return value


class OfflineHTTPApplication:
    """One locally selected model identity, one SQLite authority, bounded work."""

    def __init__(self, backend: LocalDesktopModel, database: str | Path,
                 *, token: str) -> None:
        if not isinstance(token, str) or len(token) < 32:
            raise OfflineHTTPError(400, "a strong authorization token is required")
        self.backend = backend
        self.database = Path(database)
        self.token = token
        self.model_digest = backend.model_digest
        self.tokenizer_digest = _model_tokenizer_digest(backend)
        self._lock = threading.RLock()
        self._store = OfflineChatStore(database)

    def close(self) -> None:
        self._store.close()

    def authenticate(self, authorization: str | None) -> bool:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            return False
        candidate = authorization[7:]
        return len(candidate) == len(self.token) and hmac.compare_digest(
            candidate.encode("utf-8"), self.token.encode("utf-8")
        )

    def _session(self, session_id: str):
        return self._store.load(
            _identifier("session id", session_id),
            self.model_digest, self.tokenizer_digest,
        )

    @property
    def default_output_tokens(self) -> int:
        if hasattr(self.backend, "runtime"):
            limits = self.backend.runtime.limits
            return min(32, limits.max_new_tokens, max(1, limits.max_context // 4))
        return min(32, max(1, (self.backend.config.context_size or 4096) // 4))

    def _perform_turn(self, session_id: str,
                      request: dict[str, Any]) -> dict[str, Any]:
        _fields(request, {"message", "request_id", "max_output_tokens"},
                {"message", "request_id"})
        text = request["message"]
        if (not isinstance(text, str) or not text.strip()
                or len(text.encode("utf-8", errors="strict")) > 4096):
            raise OfflineHTTPError(400, "message must contain 1–4096 UTF-8 bytes")
        text = text.strip()
        rid = _identifier("request id", request["request_id"])
        budget = _budget(request, self.default_output_tokens)
        digest = _digest_request(text, GenerationConfig(max_new_tokens=budget))
        with self._lock:
            current = self._session(session_id)
            replay = self._store.replay(session_id, rid, digest)
            if replay is not None:
                return {
                    "session_id": session_id, "request_id": rid,
                    "revision": replay.revision, "text": replay.text,
                    "output_digest": replay.output_digest,
                    "input_tokens": replay.prompt_tokens,
                    "output_tokens": replay.generated_tokens,
                    "replayed": True, "model_digest": self.model_digest,
                }
            chat = DurableOfflineAISession(
                self.backend, database=self.database, session_id=session_id
            )
            try:
                # Runtime adaptation and durability CAS are controlled by
                # DurableOfflineAISession. A failed turn leaves no partial text.
                asyncio.run(chat.ask(text, max_output_tokens=budget, request_id=rid))
            finally:
                chat.close()
            receipt = self._store.replay(session_id, rid, digest)
            if receipt is None or receipt.revision != current.revision + 1:
                raise RuntimeContractError("local generation receipt was not committed")
            return {
                "session_id": session_id, "request_id": rid,
                "revision": receipt.revision, "text": receipt.text,
                "output_digest": receipt.output_digest,
                "input_tokens": receipt.prompt_tokens,
                "output_tokens": receipt.generated_tokens,
                "replayed": False, "model_digest": self.model_digest,
            }

    def dispatch(self, method: str, path: str,
                 body: dict[str, Any] | None = None,
                 *, raw_body: bytes | None = None) -> tuple[int, Any]:
        if method not in {"GET", "POST", "DELETE"}:
            raise OfflineHTTPError(405, "unsupported local API method")
        if body is None:
            body = {}
        if path == "/v1/status" and method == "GET":
            return 200, {
                "local_only": True, "ready": True,
                "runtime_kind": ("native" if hasattr(self.backend, "runtime")
                                 else "llama.cpp"),
                "model_digest": self.model_digest,
                "tokenizer_digest": self.tokenizer_digest,
                "session_list_limit": 100,
                "default_output_tokens": self.default_output_tokens,
            }
        if path == "/v1/sessions":
            if method == "GET":
                return 200, {"sessions": [
                    {"session_id": sid, "revision": revision}
                    for sid, revision in self._store.list_sessions(
                        self.model_digest, self.tokenizer_digest
                    )
                ]}
            if method == "POST":
                _fields(body, {"system"}, set())
                system = body.get("system")
                if system is not None and (
                    not isinstance(system, str) or not system.strip()
                    or len(system.encode("utf-8")) > 4096
                ):
                    raise OfflineHTTPError(400, "invalid system instruction")
                sid = self._store.create(
                    self.model_digest, self.tokenizer_digest, system=system
                )
                return 201, {"session_id": sid, "revision": 0}
        if path == "/v1/sessions/import" and method == "POST":
            if raw_body is None:
                raise OfflineHTTPError(400, "missing portable conversation data")
            sid = self._store.import_bundle(
                raw_body, self.model_digest, self.tokenizer_digest
            )
            return 201, {"session_id": sid, "revision": self._session(sid).revision}
        components = path.split("/")
        if (len(components) not in {4, 5} or
                components[:3] != ["", "v1", "sessions"]):
            raise OfflineHTTPError(404, "unknown local API route")
        sid = _identifier("session id", components[3])
        tail = components[4] if len(components) == 5 else None
        if tail is None:
            if method == "GET":
                stored = self._session(sid)
                return 200, {
                    "session_id": sid, "revision": stored.revision,
                    "messages": stored.transcript.to_list(),
                }
            if method == "DELETE":
                self._store.delete(sid, self.model_digest,
                                   self.tokenizer_digest)
                return 200, {"deleted_session_id": sid}
        if tail == "turn" and method == "POST":
            return 200, self._perform_turn(sid, body)
        if tail == "fork" and method == "POST":
            _fields(body, {"after_turn"}, set())
            new_sid = self._store.fork(
                sid, self.model_digest, self.tokenizer_digest,
                after_turn=body.get("after_turn"),
            )
            return 201, {
                "session_id": new_sid, "source_session_id": sid,
                "revision": self._session(new_sid).revision,
            }
        if tail == "export" and method == "GET":
            return 200, self._store.export_bundle(
                sid, self.model_digest, self.tokenizer_digest
            )
        raise OfflineHTTPError(404, "unknown local API route")


class LocalOnlyHTTPServer(ThreadingHTTPServer):
    # Do not close SQLite while a live inference worker still owns a
    # model-bound transaction. Server close waits for bounded request threads.
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = False
    request_queue_size = 32

    def __init__(self, app: OfflineHTTPApplication, *, port: int = 0):
        if type(port) is not int or not 0 <= port <= 65535:
            raise OfflineHTTPError(400, "invalid localhost port")
        self.application = app
        self._capacity = threading.BoundedSemaphore(MAX_CONNECTIONS)
        # Hard-coded numeric loopback binding. Never accept host parameters.
        super().__init__(("127.0.0.1", port), OfflineHTTPHandler)

    def process_request(self, request, client_address):
        if not self._capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._capacity.release()


class OfflineHTTPHandler(BaseHTTPRequestHandler):
    server: LocalOnlyHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "SkeletonLocalAI"
    sys_version = ""

    def setup(self):
        super().setup()
        # Reject indefinitely stalled partial HTTP bodies. This protects
        # the bounded loopback worker pool from idle socket exhaustion.
        self.connection.settimeout(15.0)

    def log_message(self, format, *args):
        # Do not log conversation content, tokens or session identifiers.
        return

    def _write(self, status: int, payload: bytes, *, kind: str = "application/json",
               web: bool = False) -> None:
        if len(payload) > MAX_JSON_BYTES:
            status = 503
            payload = b'{"error":"local response budget exceeded"}'
            kind = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", kind + ("; charset=utf-8"
                                                 if kind.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(payload)))
        # One request per connection: never reuse a socket after rejecting a
        # bearer token or request body that was intentionally not consumed.
        self.send_header("Connection", "close")
        self.close_connection = True
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if web:
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; base-uri 'none'; form-action 'none'; "
                             "frame-ancestors 'none'")
        else:
            self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, obj: Any) -> None:
        self._write(status, json.dumps(
            obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"))

    def _failed(self, error: OfflineHTTPError) -> None:
        self._json(error.status, {"error": str(error)})

    def _validate_host(self) -> None:
        # Duplicate Host, Content-Length, Origin, Authorization or Transfer-
        # Encoding headers are rejected before routing. No ambiguous message
        # framing, split bearer credentials or DNS rebinding.
        for name in ("Host", "Content-Length", "Content-Type", "Origin",
                     "Authorization", "Transfer-Encoding"):
            if len(self.headers.get_all(name, [])) > 1:
                raise OfflineHTTPError(400, "duplicate HTTP control header")
        expected = {f"127.0.0.1:{self.server.server_port}",
                    f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in expected:
            raise OfflineHTTPError(403, "only the configured loopback origin is permitted")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{item}" for item in expected}:
            raise OfflineHTTPError(403, "cross-origin requests are forbidden")
        if self.headers.get("Transfer-Encoding") is not None:
            raise OfflineHTTPError(400, "chunked or encoded request bodies are forbidden")

    def _read(self, path: str) -> tuple[dict[str, Any], bytes]:
        if not self.headers.get("Content-Type", "").split(";", 1)[0].strip() == "application/json":
            raise OfflineHTTPError(415, "application/json content type required")
        declared = self.headers.get("Content-Length")
        if declared is None or not declared.isascii() or not declared.isdecimal():
            raise OfflineHTTPError(411, "numeric request length required")
        limit = MAX_JSON_BYTES if path == "/v1/sessions/import" else MAX_CHAT_REQUEST_BYTES
        length = int(declared)
        if not 1 <= length <= limit:
            raise OfflineHTTPError(413, "request byte budget exceeded")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise OfflineHTTPError(400, "incomplete JSON request body")
        return _json_object(raw), raw

    def _handle(self, method: str) -> None:
        # No cookies, credentials or permissive CORS; reject DNS rebinding.
        try:
            self._validate_host()
            path_obj = urlsplit(self.path)
            path = path_obj.path
            if path_obj.query or path_obj.fragment or "%" in path or "//" in path:
                raise OfflineHTTPError(400, "invalid local request path")
            if method == "GET" and path in {"/", "/app.js", "/app.css"}:
                data, kind = {
                    "/": (HTML, "text/html"),
                    "/app.js": (JAVASCRIPT, "application/javascript"),
                    "/app.css": (CSS, "text/css"),
                }[path]
                self._write(200, data.encode("utf-8"), kind=kind, web=True)
                return
            if not self.server.application.authenticate(
                self.headers.get("Authorization")
            ):
                raise OfflineHTTPError(401, "valid local bearer token required")
            body: dict[str, Any] = {}
            raw: bytes | None = None
            if method == "POST":
                body, raw = self._read(path)
            status, result = self.server.application.dispatch(
                method, path, body, raw_body=raw
            )
            if isinstance(result, bytes):
                self._write(status, result)
            else:
                self._json(status, result)
        except OfflineHTTPError as exc:
            self._failed(exc)
        except RuntimeContractError as exc:
            label = str(exc)
            status = (404 if "unknown offline conversation" in label else
                      409 if ("revision conflict" in label
                              or "request id reused" in label) else 400)
            self._json(status, {"error": label})
        except (OfflineAIError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
        except (OSError, sqlite3.Error):
            self._json(503, {"error": "local inference or storage is unavailable"})
        except Exception:
            self._json(500, {"error": "local inference failed without commit"})

    def do_GET(self):  # noqa: N802
        self._handle("GET")

    def do_POST(self):  # noqa: N802
        self._handle("POST")

    def do_DELETE(self):  # noqa: N802
        self._handle("DELETE")

    def do_HEAD(self):  # noqa: N802
        self.close_connection = True
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_OPTIONS(self):  # noqa: N802
        self._handle("OPTIONS")

    def do_PUT(self):  # noqa: N802
        self._handle("PUT")

    def do_PATCH(self):  # noqa: N802
        self._handle("PATCH")


def smoke_offline_http_inference() -> bool:
    """End-to-end acceptance inside the *frozen* Windows executable.

    Binds an ephemeral numeric-loopback socket, authenticates with a new
    token, performs an actual native transformer turn, retries the identical
    request, verifies SQLite recovery and tears down all resources.
    No Tk, browser, Docker, network provider, external model weights or
    secret from the operator's real installation is required.
    """
    from http.client import HTTPConnection
    from tempfile import TemporaryDirectory
    from skeleton.cortex.transformer import TinyTransformer
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel

    runtime = NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer"),
        dim=8, ctx=96, seed=41, n_heads=2, n_layers=2, d_ff=16,
    ))
    backend = NativeRuntimeLocalModel(runtime)
    token = secrets.token_urlsafe(48)
    with TemporaryDirectory(prefix="skeleton-local-http-accept-") as folder:
        database = Path(folder) / "acceptance.sqlite3"
        app = OfflineHTTPApplication(backend, database, token=token)
        try:
            with LocalOnlyHTTPServer(app, port=0) as server:
                port = server.server_port
                if server.server_address[0] != "127.0.0.1":
                    return False
                worker = threading.Thread(
                    target=server.serve_forever,
                    kwargs={"poll_interval": 0.05},
                    name="skeleton-local-acceptance", daemon=True,
                )
                worker.start()
                def request(method: str, route: str, body: dict[str, Any] | None,
                            *, authenticated: bool = True) -> tuple[int, Any]:
                    headers: dict[str, str] = {}
                    if authenticated:
                        headers["Authorization"] = "Bearer " + token
                    payload = None
                    if body is not None:
                        headers["Content-Type"] = "application/json"
                        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
                    connection = HTTPConnection("127.0.0.1", port, timeout=15)
                    try:
                        connection.request(method, route, body=payload, headers=headers)
                        response = connection.getresponse()
                        status = response.status
                        data = json.loads(response.read().decode("utf-8"))
                        return status, data
                    finally:
                        connection.close()
                try:
                    denied_status, _ = request(
                        "GET", "/v1/status", None, authenticated=False
                    )
                    status, health = request("GET", "/v1/status", None)
                    if (denied_status != 401 or status != 200
                            or health.get("model_digest") != backend.model_digest):
                        return False
                    status, created = request("POST", "/v1/sessions", {})
                    if status != 201 or not created.get("session_id"):
                        return False
                    sid = created["session_id"]
                    route = "/v1/sessions/" + sid + "/turn"
                    payload = {
                        "message": "hello", "request_id": "frozen-http-smoke",
                        "max_output_tokens": 2,
                    }
                    status, first = request("POST", route, payload)
                    again_status, replay = request("POST", route, payload)
                    read_status, saved = request(
                        "GET", "/v1/sessions/" + sid, None
                    )
                    accepted = bool(
                        status == again_status == read_status == 200
                        and first["revision"] == replay["revision"] == saved["revision"] == 1
                        and first["output_digest"] == replay["output_digest"]
                        and not first["replayed"] and replay["replayed"]
                        and len(saved["messages"]) == 2
                        and len(saved["messages"][-1]["content"].strip()) > 0
                    )
                finally:
                    server.shutdown()
                    worker.join(timeout=10)
                    if worker.is_alive():
                        raise RuntimeError("offline HTTP smoke worker failed to terminate")
        finally:
            app.close()
        if not accepted:
            return False
        # A read using the live HTTP connection is NOT a recovery test.
        # Drop the entire service and its SQLite connection, then independently
        # open the store and verify the two-message turn and original receipt.
        with OfflineChatStore(database) as reopened:
            restored = reopened.load(
                sid, backend.model_digest, app.tokenizer_digest
            )
            receipt = reopened.replay(
                sid, payload["request_id"],
                _digest_request("hello", GenerationConfig(max_new_tokens=2))
            )
            return bool(
                restored.revision == 1
                and len(restored.transcript.messages) == 2
                and restored.transcript.messages[0].content == "hello"
                and restored.transcript.messages[1].content == first["text"]
                and receipt is not None
                and receipt.revision == 1
                and receipt.text == first["text"]
                and receipt.output_digest == first["output_digest"]
            )


def create_token_file(path: str | Path, *, token: str | None = None) -> str:
    """One-time owner-only secret file; a preexisting path is never overwritten."""
    token = secrets.token_urlsafe(48) if token is None else token
    if not isinstance(token, str) or len(token) < 32:
        raise OfflineHTTPError(400, "invalid local API secret")
    target = Path(path).expanduser()
    fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            writer.write(token + "\n")
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve Skeleton local AI on loopback only; no Docker/cloud."
    )
    model = parser.add_mutually_exclusive_group(required=True)
    model.add_argument("--native-checkpoint", type=Path)
    model.add_argument("--gguf-deployment", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--token-file", type=Path, required=True,
                        help="new private bearer-token file; never overwritten")
    parser.add_argument("--port", type=int, default=0,
                        help="localhost TCP port, default: OS-assigned ephemeral port")
    args = parser.parse_args(argv)
    app = None
    try:
        backend = (load_native_checkpoint(args.native_checkpoint)
                   if args.native_checkpoint is not None
                   else load_gguf_deployment(args.gguf_deployment))
        db = args.database or private_desktop_database(backend.model_digest)
        token = secrets.token_urlsafe(48)
        app = OfflineHTTPApplication(backend, db, token=token)
        # Bind before creating private credentials: a conflicting port must
        # not leave behind an unused secret file on the user's disk.
        with LocalOnlyHTTPServer(app, port=args.port) as server:
            create_token_file(args.token_file, token=token)
            print("Skeleton offline AI:", f"http://127.0.0.1:{server.server_port}/")
            print("Private bearer token file:", args.token_file)
            print("Model digest:", app.model_digest)
            # PyInstaller's --windowed Windows launcher may deliberately set
            # stdout/stderr to None. Never make local serving contingent on
            # an attached terminal.
            if sys.stdout is not None:
                sys.stdout.flush()
            server.serve_forever(poll_interval=0.25)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print("Offline HTTP startup rejected:", str(exc), file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OfflineHTTPApplication", "OfflineHTTPError", "OfflineHTTPHandler",
    "LocalOnlyHTTPServer", "create_token_file", "smoke_offline_http_inference", "main",
]
