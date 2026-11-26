"""Loopback MCP adapter for the studio office tools.

This is a JSON-RPC transport over the existing forge charter. It does not
call a model and it does not open a second office. The default bind is
loopback. A remote bind is refused unless ``SKELETON_OFFICE_ALLOW_REMOTE=1``.
"""
from __future__ import annotations

import json
import socket
import threading
from typing import Any, Callable, Mapping

from skeleton.agents.studio_office import OfficeQueue, OfficeRejected, loopback_allowed
from skeleton.api.hmac_seal import verify_seal
from skeleton.kernel.errors import SkeletonError
from skeleton.kernel.governance import get_governance
from skeleton.skills.studio_office_tools import default_tools

TOOLS: tuple[dict[str, str], ...] = (
    {"name": "doctor", "description": "Inspect the install with the existing doctor."},
    {"name": "game_build", "description": "Compile an admitted brief with build_playable_game."},
    {"name": "job_status", "description": "Read one forge job."},
    {"name": "list_projects", "description": "List the caller's projects."},
    {"name": "office_golden", "description": "Queue the catalog ash-tunnels golden brief."},
    {"name": "office_run_status", "description": "Read one office run."},
    {"name": "office_cancel", "description": "Cancel one office run."},
)
_NAMES = {item["name"] for item in TOOLS}


class OfficeMcpServer:
    """Newline-delimited JSON-RPC server for the office tools."""

    def __init__(self, queue: OfficeQueue | None = None, tools: Mapping[str, Callable[..., Any]] | None = None) -> None:
        self.queue = queue if queue is not None else OfficeQueue(tools=tools)
        self.tools = dict(default_tools() if tools is None else tools)
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def serve(self, host: str = "127.0.0.1", port: int = 0) -> tuple[str, int]:
        if not loopback_allowed(host):
            raise OfficeRejected("office_loopback_only", "remote office MCP bind is refused", status=403)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(8)
        sock.settimeout(0.2)
        self._socket = sock
        self._thread = threading.Thread(target=self._accept, name="office-mcp", daemon=True)
        self._thread.start()
        bound = sock.getsockname()
        return str(bound[0]), int(bound[1])

    def close(self) -> None:
        sock = self._socket
        self._socket = None
        if sock is not None:
            sock.close()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def handle(self, message: Mapping[str, Any], *, peer_host: str | None) -> dict[str, Any]:
        request_id = message.get("id")
        if not loopback_allowed(peer_host):
            return _error(request_id, "office_loopback_only")
        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), Mapping) else {}
        try:
            actor = _admit(params)
        except OfficeRejected as exc:
            return _error(request_id, exc.code)
        except SkeletonError:
            return _error(request_id, "charter_denied")
        try:
            if method == "tools/list":
                result = {"tools": [dict(item) for item in TOOLS]}
            elif method == "tools/call":
                result = self._call(str(params.get("name") or ""), params.get("arguments") if isinstance(params.get("arguments"), Mapping) else {}, actor, str(params.get("tenant") or "default"))
            else:
                return _error(request_id, "method_not_found")
        except OfficeRejected as exc:
            return _error(request_id, exc.code)
        except KeyError:
            return _error(request_id, "office_run_not_found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _call(self, name: str, arguments: Mapping[str, Any], actor: str, tenant: str) -> dict[str, Any]:
        if name not in _NAMES:
            raise OfficeRejected("tool_unknown", "unknown office tool")
        if name == "office_golden":
            view = self.queue.submit_golden(actor_id=actor, tenant_id=tenant, inline=True)
            return {"run": view}
        if name == "office_run_status":
            return {"run": self.queue.get(str(arguments.get("run_id") or ""), actor_id=actor, tenant_id=tenant)}
        if name == "office_cancel":
            return {"run": self.queue.cancel(str(arguments.get("run_id") or ""), actor_id=actor, tenant_id=tenant)}
        fn = self.tools.get(name)
        if fn is None:
            return {"ok": False, "code": "tool_missing"}
        output = fn(actor_id=actor, tenant_id=tenant, **dict(arguments))
        if not isinstance(output, Mapping):
            return {"ok": False, "code": "tool_output_invalid"}
        return dict(output)

    def _accept(self) -> None:
        while self._socket is not None:
            try:
                conn, address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            peer = address[0] if isinstance(address, tuple) else None
            threading.Thread(target=self._client, args=(conn, peer), daemon=True).start()

    def _client(self, conn: socket.socket, peer: str | None) -> None:
        with conn:
            buffer = b""
            conn.settimeout(2)
            while self._socket is not None:
                try:
                    chunk = conn.recv(65536)
                except TimeoutError:
                    continue
                except OSError:
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        reply = _error(None, "invalid_json")
                    else:
                        reply = self.handle(message if isinstance(message, Mapping) else {}, peer_host=peer)
                    conn.sendall(json.dumps(reply, default=str).encode("utf-8") + b"\n")


def _admit(params: Mapping[str, Any]) -> str:
    weight = params.get("actor_weight", 0)
    if isinstance(weight, bool) or not isinstance(weight, int):
        raise OfficeRejected("invalid_actor_weight", "actor_weight must be an integer", status=400)
    try:
        actor = verify_seal(params.get("seal") if isinstance(params.get("seal"), str) else None)
    except SkeletonError as exc:
        raise OfficeRejected("charter_denied", "forge seal was rejected", status=401) from exc
    decision = get_governance().decide("forge", "run", weight)
    if not decision.permitted:
        raise OfficeRejected("charter_denied", "forge charter denied this actor", status=403)
    return actor


def _error(request_id: Any, code: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code}}
