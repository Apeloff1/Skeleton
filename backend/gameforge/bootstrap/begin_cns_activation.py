#!/usr/bin/env python3
"""CNS activation backed by the canonical registry and validated topology.

This entry point materializes room/agent/seat records, not model processes.
Operational RAG, orchestration, and external I/O require separate evidence.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from gameforge.bootstrap.full_room_agent_bootstrap import FullRoomAgentBootstrap
from gameforge.rooms.full_room_registry import all_rooms


def _category(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid registry division")
    category = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.-")
    if not category:
        raise ValueError("invalid registry division")
    return category


class BeginCNSActivation:
    def __init__(self):
        self._lock = RLock()
        self._bootstrap = FullRoomAgentBootstrap()
        self.start_time = None
        self.rooms_instantiated = 0
        self.agents_spawned = 0
        self.errors: list[str] = []
        self.status = "NOT_ACTIVATED"
        self._latest: dict[str, Any] | None = None

    def run(self) -> dict:
        with self._lock:
            self.start_time = datetime.now(timezone.utc)
            try:
                registry = all_rooms()
                # All declared rooms must be accounted for. No synthetic IDs,
                # fallback agent counts, or swallowed import failures.
                manifest = [
                    {
                        "room_id": rid,
                        "category": _category(meta.get("division", "Other")),
                        "role": meta.get("role", "generalist"),
                        "seats": 8,
                    }
                    for rid, meta in registry.items()
                ]
                topology = self._bootstrap.bootstrap(manifest, [])
                self.rooms_instantiated = topology["rooms_instantiated"]
                self.agents_spawned = topology["agents_spawned"]
                self.errors = []
                self.status = topology["overall_status"]
            except (TypeError, ValueError, KeyError, AttributeError):
                self.errors = ["registry_topology_invalid"]
                self.status = "DEGRADED"
                topology = self._bootstrap.snapshot()
            self._latest = self._make_report(topology)
            return self.status_report()

    def _make_report(self, topology: dict) -> dict:
        return {
            "rooms": self.rooms_instantiated,
            "agents": self.agents_spawned,
            "bindings": topology["bindings"],
            "rooms_without_agents": topology["rooms_without_agents"],
            "topology_sha256": topology["topology_sha256"],
            "generation": topology["generation"],
            "indexes": "registry_loaded" if not self.errors else "unavailable",
            "bookshelf": "unqualified",
            "coherence": topology["coherence"],
            "synergy": "unqualified",
            "rag": "unqualified",
            "orchestrator": "unqualified",
            "runtime_qualified": False,
            "errors": list(self.errors),
            "overall_status": self.status,
        }

    def status_report(self) -> dict:
        with self._lock:
            if self._latest is None:
                return {
                    "rooms": 0, "agents": 0, "bindings": 0, "generation": 0,
                    "runtime_qualified": False, "overall_status": "NOT_ACTIVATED",
                    "errors": [],
                }
            return {**self._latest, "errors": list(self._latest["errors"])}

    def inventory(self) -> dict:
        with self._lock:
            return self._bootstrap.snapshot()


_ACTIVATION = BeginCNSActivation()


def get_activation() -> BeginCNSActivation:
    """Process-owned topology used by both the cockpit and activation API."""
    return _ACTIVATION


if __name__ == "__main__":
    print(json.dumps(get_activation().run(), indent=2))
