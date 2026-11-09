"""
Skeleton Galaxy — Cross-node task routing

Extends the swarm bridge across the galaxy wire: when no local agent
can serve a capability, the task is offered to remote nodes that
advertise it. Remote execution is acknowledged over the transport;
results return via callback message.

Wire messages:
- task.offer    {task_id, specialisation, description, from}
- task.accept   {task_id, node_id}
- task.result   {task_id, node_id, result, ok}

Provides:
- GalaxyBridge: route tasks local-first, fall back to remote nodes
- RemoteTask: tracked remote assignment
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RemoteTask:
    """A task assigned to a remote galaxy node."""
    task_id: str
    specialisation: str
    description: str
    offered_to: str = ""
    accepted_by: str = ""
    status: str = "offered"  # offered | accepted | completed | failed | expired
    result: Any = None
    offered_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def is_open(self) -> bool:
        return self.status in ("offered", "accepted")


class GalaxyBridge:
    """Route Coordinator tasks local-first, galaxy-wide as fallback.

    Composes the local MeshBridge: try the local swarm first; only
    when no local agent can serve the capability does the task go
    on the wire. Remote handlers register via `serve(capability, fn)`.
    """

    OFFER_TTL = 10.0  # seconds an offer stays open without acceptance

    def __init__(self, mesh_bridge: Any, node: Any, transport: Any, bus: Optional[Any] = None):
        self._local = mesh_bridge
        self._node = node
        self._transport = transport
        self._bus = bus
        self._remote_tasks: Dict[str, RemoteTask] = {}
        self._services: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._stats = {"local": 0, "offered": 0, "accepted": 0, "completed": 0,
                       "failed": 0, "served": 0}

        transport.on("task.offer", self._on_offer)
        transport.on("task.accept", self._on_accept)
        transport.on("task.result", self._on_result)

    # --- Service side (this node executes for others) -------------------

    def serve(self, capability: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        """Advertise a capability this node executes on request."""
        self._services[capability] = handler
        self._node.add_capability(capability)

    def _on_offer(self, payload: Dict[str, Any]) -> None:
        """A remote node offers us a task: accept if we serve the capability."""
        spec = payload.get("specialisation", "")
        handler = self._services.get(spec)
        if handler is None:
            return
        sender = self._node._registry._nodes.get(payload.get("from"))
        if sender is None:
            return

        task_id = payload["task_id"]
        self._transport.send(sender.address, {
            "type": "task.accept",
            "task_id": task_id,
            "node_id": self._node.node_id,
        })

        # Execute and return the result
        ok, result = True, None
        try:
            result = handler({"task_id": task_id, "description": payload.get("description", "")})
        except Exception as e:
            ok, result = False, str(e)

        self._stats["served"] += 1
        self._transport.send(sender.address, {
            "type": "task.result",
            "task_id": task_id,
            "node_id": self._node.node_id,
            "result": result,
            "ok": ok,
        })

    # --- Client side (this node routes tasks) ----------------------------

    def dispatch(self, task: Any, specialisation: str) -> bool:
        """Local-first dispatch; galaxy fallback when no local agent serves."""
        if self._local.dispatch(task, specialisation):
            self._stats["local"] += 1
            return True
        return self.offer_remote(task, specialisation)

    def offer_remote(self, task: Any, specialisation: str) -> bool:
        """Offer a task to remote nodes advertising the capability."""
        candidates = [
            n for n in self._node._registry.discover(capability=specialisation)
        ]
        if not candidates:
            self._stats["failed"] += 1
            return False

        remote = RemoteTask(
            task_id=task.task_id,
            specialisation=specialisation,
            description=getattr(task, "description", ""),
            offered_to=candidates[0].node_id,
        )
        self._remote_tasks[task.task_id] = remote
        self._stats["offered"] += 1

        task.metadata["galaxy_offered_to"] = candidates[0].node_id
        self._transport.send(candidates[0].address, {
            "type": "task.offer",
            "task_id": task.task_id,
            "specialisation": specialisation,
            "description": remote.description,
            "from": self._node.node_id,
        })

        if self._bus:
            self._bus.emit("galaxy.task.offered", {
                "task_id": task.task_id,
                "specialisation": specialisation,
                "offered_to": candidates[0].node_id,
            })
        return True

    def _on_accept(self, payload: Dict[str, Any]) -> None:
        remote = self._remote_tasks.get(payload["task_id"])
        if remote is None or not remote.is_open():
            return
        remote.status = "accepted"
        remote.accepted_by = payload.get("node_id", "")
        self._stats["accepted"] += 1

    def _on_result(self, payload: Dict[str, Any]) -> None:
        remote = self._remote_tasks.get(payload["task_id"])
        if remote is None:
            return
        remote.status = "completed" if payload.get("ok") else "failed"
        remote.result = payload.get("result")
        remote.completed_at = time.time()
        self._stats["completed" if payload.get("ok") else "failed"] += 1

        if self._bus:
            self._bus.emit("galaxy.task.completed", {
                "task_id": remote.task_id,
                "node_id": payload.get("node_id"),
                "ok": bool(payload.get("ok")),
            })

    def wait_result(self, task_id: str, timeout: float = 5.0) -> Optional[RemoteTask]:
        """Block until a remote task resolves or times out."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            remote = self._remote_tasks.get(task_id)
            if remote is not None and not remote.is_open():
                return remote
            time.sleep(0.05)
        return self._remote_tasks.get(task_id)

    def expire_offers(self) -> int:
        """Mark stale un-accepted offers expired. Returns count."""
        now = time.time()
        expired = 0
        for remote in self._remote_tasks.values():
            if remote.status == "offered" and now - remote.offered_at > self.OFFER_TTL:
                remote.status = "expired"
                expired += 1
        return expired

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "open_remote": sum(1 for r in self._remote_tasks.values() if r.is_open())}
