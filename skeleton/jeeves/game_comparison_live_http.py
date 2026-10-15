"""Local-only authenticated HTTP facade for actual live comparison lanes.

Not a public multi-user service. Binding is hardcoded to IPv4 loopback and
POST always requires a process-random header token plus same-origin check.
The browser never submits paths, core IDs, firmware, command strings or ROM
bytes. Native execution remains in isolated libretro worker subprocesses.
"""
from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .game_comparison_live import LiveComparison

SCHEMA = "skeleton.game.local_live_http.v1"
MAX_REQUEST = 64 * 1024
MAX_IDLE_SECONDS = 3600


class LocalComparisonServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, session: LiveComparison, port: int, idle_seconds: int):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("HTTP port is outside 0–65535")
        if type(idle_seconds) is not int or not 60 <= idle_seconds <= MAX_IDLE_SECONDS:
            raise ValueError("Local studio idle cutoff must be between 60 and 3600 seconds")
        self.session = session
        self.secret = secrets.token_hex(32)
        self.nonce = secrets.token_hex(16)
        self.idle_seconds = idle_seconds
        self.last_active = time.monotonic()
        self.stopping = threading.Event()
        super().__init__(("127.0.0.1", port), LocalComparisonHandler)

    def stop(self) -> None:
        if self.stopping.is_set():
            return
        self.stopping.set()
        self.shutdown()
        self.session.close()

    def monitor_idle(self) -> None:
        while not self.stopping.wait(5):
            if time.monotonic() - self.last_active >= self.idle_seconds:
                self.stop()
                return


class LocalComparisonHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: LocalComparisonServer

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not log bearer credential or private operator content.
        return

    def _check_host(self) -> bool:
        return self.headers.get("Host", "") == "127.0.0.1:" + str(self.server.server_port)

    def _response(self, data: bytes, *, content_type: str, status: int = 200, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'nonce-" + self.server.nonce +
                         "'; style-src 'nonce-" + self.server.nonce +
                         "'; img-src data:; media-src blob:; connect-src 'self'; base-uri 'none'; object-src 'none'; form-action 'none'; frame-ancestors 'none'")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value: object, status: int = 200) -> None:
        data = json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        self._response(data,content_type="application/json; charset=utf-8",status=status)

    def _error(self, message: str, status: int) -> None:
        self._json({"status":"rejected","reason":message},status)

    def _authorized(self, *, mutating: bool) -> bool:
        if not self._check_host():
            self._error("Host is not the loopback session origin",403)
            return False
        token=self.headers.get("X-Study-Token", "")
        if not hmac.compare_digest(token,self.server.secret):
            self._error("Invalid local study authorization",403)
            return False
        if mutating:
            expected="http://127.0.0.1:" + str(self.server.server_port)
            if self.headers.get("Origin")!=expected:
                self._error("Cross-origin live core input is forbidden",403)
                return False
            if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
                self._error("Only bounded application/json commands are allowed",415)
                return False
        self.server.last_active=time.monotonic()
        return True

    def do_GET(self) -> None:
        if not self._check_host():
            self._error("Invalid local host authority",403)
            return
        if self.path=="/":
            from .game_comparison_live_viewer import render_live_comparison_page
            data=render_live_comparison_page(self.server.secret,self.server.nonce).encode()
            self.server.last_active=time.monotonic()
            self._response(data,content_type="text/html; charset=utf-8")
        elif self.path=="/api/state":
            if self._authorized(mutating=False):
                try:
                    self._json(self.server.session.state())
                except (ValueError,RuntimeError) as exc:
                    self._error(type(exc).__name__,409)
        elif self.path=="/api/evidence":
            if self._authorized(mutating=False):
                try:
                    self._json(self.server.session.export_evidence())
                except (ValueError,RuntimeError) as exc:
                    self._error(type(exc).__name__,409)
        else:
            self._error("Unknown local studio endpoint",404)

    def do_POST(self) -> None:
        if self.path not in ("/api/step","/api/reset","/api/disc_swap","/api/stop"):
            self._error("Unknown local native action",404)
            return
        if not self._authorized(mutating=True):
            return
        size=self.headers.get("Content-Length")
        try:
            length=int(size) if size is not None else -1
        except (ValueError,TypeError):
            length=-1
        if not 2 <= length <= MAX_REQUEST:
            self.close_connection=True
            self._error("Native control request must be 2–65536 bytes",413)
            return
        raw=self.rfile.read(length)
        try:
            from .game_comparison_schema import parse_json
            packet=parse_json(raw,limit=MAX_REQUEST)
            if self.path=="/api/step":
                value=self.server.session.step(packet)
            elif self.path=="/api/reset":
                if not isinstance(packet,dict) or set(packet)!={"game_id"}:
                    raise ValueError("Reset command needs one exact game_id")
                value=self.server.session.reset(packet["game_id"])
            elif self.path=="/api/disc_swap":
                value=self.server.session.swap_disc(packet)
            else:
                if packet!={}:
                    raise ValueError("Stop command cannot submit extra operations")
                value={"status":"stopping_native_studio"}
                self._json(value)
                threading.Thread(target=self.server.stop,daemon=True).start()
                return
            self._json(value)
        except (ValueError,RuntimeError,OSError) as exc:
            # No privileged path/core/worker error text crosses the UI boundary.
            self._error(type(exc).__name__,400)

    def do_OPTIONS(self) -> None:
        self._error("Cross-origin preflights are not permitted",403)
