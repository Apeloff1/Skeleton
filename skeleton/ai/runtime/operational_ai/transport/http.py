"""Bounded, bearer-authenticated loopback-only HTTP transport.

The on-device AI cannot be allowed to create an unauthenticated or unbounded
socket service. Reject browser origins, ambiguous framing, request smuggling,
unknown routes, duplicate singleton headers, slow clients and excess active
connections. The caller remains responsible for strong token custody.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import ipaddress
import json
import socket
import threading

from ..authority.canonical import ContractViolation
from .protocol import parse_request, response, MAX_BODY
from .dispatch import Dispatcher


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    block_on_close = True

    def __init__(self, address: tuple[str, int], dispatcher: Dispatcher,
                 token: str, *, max_connections: int = 8,
                 io_timeout_seconds: float = 15.0):
        host, port = address
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ContractViolation("local API requires literal loopback IP") from exc
        if not ip.is_loopback or type(port) is not int or not 0 <= port <= 65535:
            raise ContractViolation("public API binding refused")
        if (type(token) is not str or not 32 <= len(token) <= 512
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise ContractViolation("bearer secret must be strong, printable and bounded")
        if type(max_connections) is not int or not 1 <= max_connections <= 64:
            raise ContractViolation("invalid HTTP concurrency ceiling")
        if (type(io_timeout_seconds) not in (int, float)
                or not 1 <= io_timeout_seconds <= 120):
            raise ContractViolation("invalid local HTTP I/O deadline")
        self.dispatcher = dispatcher
        self.bearer = token.encode("ascii")
        self.io_timeout_seconds = float(io_timeout_seconds)
        self._slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, RequestHandler)

    def process_request(self, request: socket.socket,
                        client_address: tuple[str, int]) -> None:
        if not self._slots.acquire(blocking=False):
            # Refusal has no request parser or heavyweight worker allocation.
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request: socket.socket,
                               client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class RequestHandler(BaseHTTPRequestHandler):
    server: LocalHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        self.request.settimeout(self.server.io_timeout_seconds)
        super().setup()

    def log_message(self, *_args: object) -> None:
        # Private prompts, authorization headers and URL strings stay out of logs.
        return

    def handle_expect_100(self) -> bool:
        # Never send 100 Continue before bearer/framing validation.
        self.send_error(417, "expectation rejected")
        self.close_connection = True
        return False

    def _write(self, code: int, status: str, result: dict) -> None:
        raw = response(status, result)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def _headers_safe(self) -> bool:
        # RFC framing ambiguity must not be delegated to a second parser.
        singletons = ("Host", "Authorization", "Content-Length", "Content-Type",
                      "Transfer-Encoding", "Expect", "Origin")
        if any(len(self.headers.get_all(key, [])) > 1 for key in singletons):
            return False
        for name, value in self.headers.raw_items():
            if (not name.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in name)
                    or "\r" in value or "\n" in value or "\0" in value):
                return False
        if self.headers.get("Transfer-Encoding") is not None:
            return False
        if self.headers.get("Expect") is not None:
            return False
        return True

    def _authorize(self) -> bool:
        if not self._headers_safe():
            self._write(400, "bad-request", {"reason": "ambiguous-request-framing"})
            return False
        host = self.headers.get("Host", "")
        allowed_host = f"{self.server.server_address[0]}:{self.server.server_address[1]}"
        if host != allowed_host:
            self._write(403, "denied", {"reason": "host-rejected"})
            return False
        if self.headers.get("Origin") is not None:
            self._write(403, "denied", {"reason": "browser-origin-not-accepted"})
            return False
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if not hmac.compare_digest(token.encode("utf-8"), self.server.bearer):
            self._write(401, "denied", {"reason": "bearer-required"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._authorize():
            return
        if self.path != "/v1/protocol":
            self._write(404, "bad-request", {"reason": "unknown-route"})
            return
        from .protocol import schema
        self._write(200, "ok", schema())

    def do_POST(self) -> None:
        if not self._authorize():
            return
        if self.path != "/v1/operations":
            self._write(404, "bad-request", {"reason": "unknown-route"})
            return
        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";")[0].strip().lower() != "application/json":
            self._write(415, "bad-request", {"reason": "json-required"})
            return
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
            self._write(413, "bad-request", {"reason": "body-size-invalid"})
            return
        try:
            raw = self.rfile.read(int(length))
            if len(raw) != int(length):
                raise ContractViolation("malformed request length")
            operation, payload = parse_request(raw)
            data = self.server.dispatcher.dispatch(operation, payload)
            self._write(200, "ok", data)
        except ContractViolation:
            self._write(400, "bad-request", {"reason": "contract-rejected"})
        except Exception:
            self._write(500, "error", {"reason": "operation-failed"})
