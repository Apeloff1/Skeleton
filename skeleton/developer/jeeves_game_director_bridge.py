"""Explicit loopback-only Godot <-> canonical Director gameplay transport.

The local Python Director runtime remains the sole authority for quests, state,
inventory and outcomes. This server has no internet access, no CORS permission,
no remote binding, no implicit session creation and no silent provider fallback.
Launch only with the explicit user-supplied bearer secret from an environment
variable. Never emit the token into logs or files.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any

from skeleton.developer.jeeves_game_director_session import inspect, choose

SCHEMA = "skeleton.jeeves.director_loopback.v1"
MAX_REQUEST = 4096
MAX_RESPONSE = 2 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
ENV = "SKELETON_DIRECTOR_BRIDGE_TOKEN"


def _secret_from_env() -> str:
    secret = os.environ.get(ENV)
    if (not isinstance(secret, str) or not 32 <= len(secret) <= 256
            or not secret.isascii() or not secret.isprintable()
            or any(char.isspace() for char in secret)):
        raise ValueError("Set a non-whitespace 32..256 character ASCII " + ENV +
                         " secret before starting the local gameplay bridge")
    return secret


def _valid_port(port: int) -> int:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Director loopback service port must be 1024..65535")
    return port


def handler(root: Path, session: str, token: str, port: int,
            policy_digest: str | None = None) -> type[BaseHTTPRequestHandler]:
    """Create isolated request handler with no shared mutable game-state cache."""
    if port != 0:
        _valid_port(port)
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        raise ValueError("invalid Director bridge authorization token")
    # Session replay is the authority; refuse to serve a corrupt or foreign game.
    inspect(root, session=session)
    if policy_digest is not None:
        from skeleton.developer.jeeves_game_dragon_policy import predict
        predict(root, session=session, digest=policy_digest)

    class DirectorHandler(BaseHTTPRequestHandler):
        server_version = "JeevesDirector"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Headers/tokens are never included in stdout or CI/mail logs.
            return None

        def _answer(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body, sort_keys=True, ensure_ascii=True,
                             allow_nan=False).encode("ascii")
            if len(raw) > MAX_RESPONSE:
                raw = b'{"ok":false,"error":"response too large"}'
                status = 507
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def _admit(self) -> bool:
            # Resist DNS rebinding, ambient browser credentials and cross-origin
            # requests. Godot HTTPRequest does not require browser CORS headers.
            host_values = self.headers.get_all("Host", [])
            host = host_values[0] if len(host_values) == 1 else None
            actual_port = self.server.server_port
            if host not in {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}:
                self._answer(403, {"ok": False, "error": "loopback Host only"})
                return False
            if self.headers.get("Origin") is not None or (
                self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin")
            ):
                self._answer(403, {"ok": False, "error": "browser origins not supported"})
                return False
            credentials = self.headers.get_all("Authorization", [])
            provided = credentials[0] if len(credentials) == 1 else ""
            if not provided.isascii() or not hmac.compare_digest(provided, "Bearer " + token):
                self._answer(401, {"ok": False, "error": "unauthorized"})
                return False
            return True

        def do_GET(self) -> None:
            if not self._admit():
                return
            if self.path == "/v1/health":
                self._answer(200, {"ok": True, "schema": SCHEMA,
                                   "authoritative_runtime": "Python Director",
                                   "native_engine_e2e_verified": False})
                return
            if self.path == "/v1/advice":
                if policy_digest is None:
                    self._answer(404, {"ok": False, "error": "Dragon micro-model not enabled"})
                    return
                try:
                    from skeleton.developer.jeeves_game_dragon_policy import predict
                    advice = predict(root, session=session, digest=policy_digest)
                    self._answer(200, {"ok": True, "schema": SCHEMA, "advice": advice})
                except (OSError, ValueError, KeyError, TypeError):
                    self._answer(409, {"ok": False, "error": "Dragon model evidence is stale or invalid"})
                return
            if self.path != "/v1/status":
                self._answer(404, {"ok": False, "error": "unknown endpoint"})
                return
            try:
                snapshot = inspect(root, session=session)
                self._answer(200, {"ok": True, "schema": SCHEMA, "snapshot": snapshot})
            except (OSError, ValueError, KeyError, TypeError):
                self._answer(409, {"ok": False, "error": "session integrity or source mismatch"})

        def do_POST(self) -> None:
            if not self._admit():
                return
            if self.path != "/v1/actions":
                self._answer(404, {"ok": False, "error": "unknown endpoint"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self._answer(415, {"ok": False, "error": "JSON content type required"})
                return
            size_values = self.headers.get_all("Content-Length", [])
            size = size_values[0] if len(size_values) == 1 else ""
            if (self.headers.get("Transfer-Encoding") is not None
                    or len(size) > 5 or not size.isascii() or not size.isdecimal()
                    or not 1 <= int(size) <= MAX_REQUEST):
                self._answer(413, {"ok": False, "error": "invalid action request size"})
                return
            try:
                payload = json.loads(self.rfile.read(int(size)).decode("utf-8"),
                                     object_pairs_hook=_reject_duplicates,
                                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            except (UnicodeError, ValueError, RecursionError):
                self._answer(400, {"ok": False, "error": "invalid action JSON"})
                return
            if (not isinstance(payload, dict) or set(payload) != {
                    "choice", "expected_sequence", "expected_state_sha256"}
                    or not isinstance(payload["choice"], str)
                    or not 1 <= len(payload["choice"]) <= 140
                    or type(payload["expected_sequence"]) is not int
                    or not isinstance(payload["expected_state_sha256"], str)
                    or not HEX.fullmatch(payload["expected_state_sha256"])):
                self._answer(400, {"ok": False, "error": "invalid action shape"})
                return
            try:
                current = inspect(root, session=session)
                if (current["sequence"] != payload["expected_sequence"]
                        or current["current_state_sha256"] != payload["expected_state_sha256"]):
                    self._answer(409, {"ok": False, "error": "stale game state",
                                       "snapshot": current})
                    return
                result = choose(
                    root, session=session, choice=payload["choice"],
                    expected_sequence=payload["expected_sequence"],
                    expected_state_sha256=payload["expected_state_sha256"],
                )
                try:
                    from skeleton.developer.jeeves_game_director_events import delta
                    presentation = delta(root, session=session, before=current, after=result)
                    presentation_error = None
                except (ValueError, OSError, KeyError, TypeError):
                    # The quest action was already committed. Never report that
                    # it failed just because the optional presentation layer
                    # could not generate/validate its cinematic cues.
                    presentation = None
                    presentation_error = "re-check presentation from authoritative session"
                self._answer(200, {
                    "ok": True, "schema": SCHEMA, "snapshot": result,
                    "presentation": presentation, "presentation_warning": presentation_error,
                })
            except (ValueError, OSError, KeyError, TypeError):
                self._answer(409, {"ok": False, "error": "unavailable action or invalid game session"})

        def do_OPTIONS(self) -> None:
            self._answer(405, {"ok": False, "error": "CORS is disabled"})

    return DirectorHandler


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate action JSON key")
        result[key] = value
    return result


class _LoopbackServer(HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(10)
        return sock, addr


def serve(root: Path, *, session: str, port: int = 8765,
          policy_digest: str | None = None) -> dict[str, Any]:
    """Foreground, single-threaded, local-only gameplay for an existing session."""
    port = _valid_port(port)
    token = _secret_from_env()
    endpoint = f"http://127.0.0.1:{port}"
    listener = handler(root, session, token, port, policy_digest=policy_digest)
    with _LoopbackServer(("127.0.0.1", port), listener) as service:
        print(json.dumps({
            "ok": True, "action": "director-serve", "endpoint": endpoint,
            "session": session, "transport": SCHEMA,
            "optional_dragon_policy_enabled": policy_digest is not None,
            "bearer_token_from_env": ENV,
            "token_logged": False, "native_engine_run_verified": False,
            "note": "Foreground service; stop with Ctrl+C",
        }, sort_keys=True), flush=True)
        try:
            service.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
    return {"ok": True, "action": "director-serve", "stopped": True,
            "session": session, "native_engine_playtest_verified": False}
