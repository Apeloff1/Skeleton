"""
Skeleton Galaxy — HTTP transport for cross-node messaging

Gives GalaxyNode a real wire protocol:
- NodeTransport: HTTP inbox/outbox between galaxy nodes
- Message envelopes signed with the node's id; peers tracked via registry

Design: stdlib-only (http.server + urllib) so it runs anywhere with
zero extra deps. Each node runs a tiny HTTP server on its address;
messages POST to /galaxy/message, heartbeats to /galaxy/heartbeat.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional


class _InboxHandler(BaseHTTPRequestHandler):
    """HTTP handler for incoming galaxy messages."""

    transport: "NodeTransport" = None  # injected by NodeTransport.start

    def log_message(self, format: str, *args) -> None:  # silence request logs
        pass

    def _reply(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._reply(400, {"error": "invalid_json"})

        if self.path == "/galaxy/message":
            accepted = self.transport.receive(data)
            return self._reply(200 if accepted else 400, {"accepted": accepted})

        if self.path == "/galaxy/heartbeat":
            ok = self.transport.receive_heartbeat(data.get("node_id", ""))
            return self._reply(200 if ok else 404, {"alive": ok})

        self._reply(404, {"error": "unknown_path"})

    def do_GET(self) -> None:
        if self.path == "/galaxy/status":
            return self._reply(200, self.transport.status())
        self._reply(404, {"error": "unknown_path"})


class NodeTransport:
    """HTTP transport binding a GalaxyNode to a real address.

    `start()` spawns the inbox server on a daemon thread; `send()`
    POSTs envelopes to peers. Falls back silently when a peer is
    unreachable — the mesh's local outbox still records the intent.
    """

    def __init__(self, node: Any, host: str = "127.0.0.1", port: int = 0):
        self._node = node  # GalaxyNode
        self.host = host
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._inbox: List[Dict[str, Any]] = []
        self._handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._stats = {"sent": 0, "received": 0, "failed": 0, "heartbeats": 0}

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def on(self, message_type: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a handler for an envelope payload 'type'."""
        self._handlers[message_type] = handler

    def start(self) -> "NodeTransport":
        """Start the inbox server. Port 0 picks a free ephemeral port."""
        _InboxHandler.transport = self
        self._server = HTTPServer((self.host, self.port), _InboxHandler)
        self.port = self._server.server_address[1]  # resolve ephemeral port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    def send(self, target_address: str, payload: Dict[str, Any], timeout: float = 2.0) -> bool:
        """Send an envelope to a peer node."""
        envelope = {
            "from": self._node.node_id,
            "from_address": self.address,
            "timestamp": time.time(),
            "payload": payload,
        }
        try:
            req = urllib.request.Request(
                f"http://{target_address}/galaxy/message",
                data=json.dumps(envelope).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ok = resp.status == 200
        except Exception:
            ok = False
        self._stats["sent" if ok else "failed"] += 1
        return ok

    def heartbeat(self, target_address: str, timeout: float = 2.0) -> bool:
        """Ping a peer with our node id."""
        try:
            req = urllib.request.Request(
                f"http://{target_address}/galaxy/heartbeat",
                data=json.dumps({"node_id": self._node.node_id}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ok = resp.status == 200
        except Exception:
            ok = False
        if ok:
            self._stats["heartbeats"] += 1
        return ok

    def receive(self, envelope: Dict[str, Any]) -> bool:
        """Handle an incoming envelope (called by the HTTP handler)."""
        if not isinstance(envelope, dict) or "payload" not in envelope:
            return False
        self._inbox.append(envelope)
        self._stats["received"] += 1

        # Auto-register the sender in the local registry
        sender_id = envelope.get("from")
        sender_addr = envelope.get("from_address")
        if sender_id and hasattr(self._node, "_registry"):
            self._node._registry.register(sender_id, sender_addr or "unknown")

        payload = envelope["payload"]
        handler = self._handlers.get(payload.get("type", ""))
        if handler:
            handler(payload)
        return True

    def receive_heartbeat(self, node_id: str) -> bool:
        """Handle an incoming heartbeat ping."""
        if hasattr(self._node, "_registry") and node_id in self._node._registry._nodes:
            self._node._registry.heartbeat(node_id)
            return True
        return False

    def inbox(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._inbox[-n:]

    def status(self) -> Dict[str, Any]:
        return {
            "node_id": self._node.node_id,
            "address": self.address,
            "stats": dict(self._stats),
            "inbox_size": len(self._inbox),
        }
