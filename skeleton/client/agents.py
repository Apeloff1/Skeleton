"""Agents client: mesh agent registration + hardened swarm runtime.

Backend: ``skeleton/api/routes.py`` (``/swarm/agent``, ``/swarm/stats``) and
``skeleton/api/swarm_routes.py`` (``/swarm`` prefix), all under ``/api/v1``.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence, TypedDict
from urllib.parse import quote

from skeleton.client.cancel import CancelToken
from skeleton.client.gateway import GatewayClient
from skeleton.client.streaming import StreamEvent, stream_events

SDK_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/swarm/agent"),
    ("GET", "/api/v1/swarm/stats"),
    ("GET", "/api/v1/swarm/status"),
    ("GET", "/api/v1/swarm/workers"),
    ("POST", "/api/v1/swarm/workers"),
    ("GET", "/api/v1/swarm/workers/{worker_id}"),
    ("POST", "/api/v1/swarm/workers/{worker_id}/heartbeat"),
    ("DELETE", "/api/v1/swarm/workers/{worker_id}"),
    ("GET", "/api/v1/swarm/tasks"),
    ("POST", "/api/v1/swarm/tasks"),
    ("GET", "/api/v1/swarm/tasks/{task_id}"),
    ("POST", "/api/v1/swarm/tasks/{task_id}/cancel"),
    ("POST", "/api/v1/swarm/tasks/{task_id}/revive"),
    ("GET", "/api/v1/swarm/events"),
)


class AgentRegistration(TypedDict):
    agent_id: str
    status: str


class SwarmWorker(TypedDict, total=False):
    id: str
    capabilities: list[str]
    capacity: int
    active: list[str]
    available: int
    accepted: int
    completed: int
    failed: int
    renewals: int
    heartbeats: int
    last_seen: float


class SwarmTask(TypedDict, total=False):
    id: str
    state: str
    payload: dict[str, Any]
    priority: int
    max_attempts: int
    required_capabilities: list[str]


def _seg(value: str) -> str:
    return quote(value, safe="")


class AgentsClient:
    """Typed client for agent/swarm routes under ``/api/v1``."""

    def __init__(self, gateway: GatewayClient) -> None:
        self._gw = gateway

    # mesh agents (routes.py)
    def register(
        self,
        specialisations: Sequence[str],
        *,
        weight: float = 1.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentRegistration:
        body: dict[str, Any] = {"specialisations": list(specialisations), "weight": weight}
        if metadata is not None:
            body["metadata"] = dict(metadata)
        return self._gw._json("POST", "/api/v1/swarm/agent", json=body)

    def mesh_stats(self) -> dict[str, Any]:
        return self._gw._json("GET", "/api/v1/swarm/stats", idempotent=True)

    # swarm runtime (swarm_routes.py)
    def status(self) -> dict[str, Any]:
        return self._gw._json("GET", "/api/v1/swarm/status", idempotent=True)

    def list_workers(self, *, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        return self._gw._json(
            "GET", "/api/v1/swarm/workers",
            params={"offset": offset, "limit": limit}, idempotent=True,
        )

    def register_worker(
        self, worker_id: str, *, capabilities: Sequence[str] = (), capacity: int = 1
    ) -> dict[str, Any]:
        return self._gw._json(
            "POST", "/api/v1/swarm/workers",
            json={"worker_id": worker_id, "capabilities": list(capabilities), "capacity": capacity},
        )

    def get_worker(self, worker_id: str) -> SwarmWorker:
        return self._gw._json("GET", f"/api/v1/swarm/workers/{_seg(worker_id)}", idempotent=True)

    def heartbeat(self, worker_id: str) -> dict[str, Any]:
        return self._gw._json("POST", f"/api/v1/swarm/workers/{_seg(worker_id)}/heartbeat")

    def unregister_worker(self, worker_id: str, *, requeue: bool = True) -> dict[str, Any]:
        return self._gw._json(
            "DELETE", f"/api/v1/swarm/workers/{_seg(worker_id)}",
            params={"requeue": str(requeue).lower()},
        )

    def list_tasks(
        self, *, state: str | None = None, offset: int = 0, limit: int = 100
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if state is not None:
            params["state"] = state
        return self._gw._json("GET", "/api/v1/swarm/tasks", params=params, idempotent=True)

    def submit_task(
        self,
        task_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        priority: int = 100,
        max_attempts: int = 3,
        required_capabilities: Sequence[str] = (),
    ) -> SwarmTask:
        return self._gw._json(
            "POST", "/api/v1/swarm/tasks",
            json={
                "task_id": task_id,
                "payload": dict(payload or {}),
                "priority": priority,
                "max_attempts": max_attempts,
                "required_capabilities": list(required_capabilities),
            },
        )

    def get_task(self, task_id: str, *, cancel: CancelToken | None = None) -> SwarmTask:
        return self._gw._json(
            "GET", f"/api/v1/swarm/tasks/{_seg(task_id)}", idempotent=True, cancel=cancel
        )

    def cancel_task(self, task_id: str, reason: str = "cancelled") -> SwarmTask:
        return self._gw._json(
            "POST", f"/api/v1/swarm/tasks/{_seg(task_id)}/cancel", json={"reason": reason}
        )

    def revive_task(self, task_id: str, *, reset_attempts: bool = False) -> SwarmTask:
        return self._gw._json(
            "POST", f"/api/v1/swarm/tasks/{_seg(task_id)}/revive",
            json={"reset_attempts": reset_attempts},
        )

    def events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """GET /api/v1/swarm/events — snapshot ``{"events": [...]}``."""
        body = self._gw._json(
            "GET", "/api/v1/swarm/events", params={"limit": limit}, idempotent=True
        )
        return list((body or {}).get("events", []))

    def stream_events(
        self,
        *,
        limit: int = 100,
        last_event_id: str | None = None,
        cancel: CancelToken | None = None,
    ) -> Iterator[StreamEvent]:
        """Iterate swarm events (JSON snapshot today; SSE/NDJSON if served)."""
        return stream_events(
            self._gw, "/api/v1/swarm/events",
            params={"limit": limit}, last_event_id=last_event_id, cancel=cancel,
        )
