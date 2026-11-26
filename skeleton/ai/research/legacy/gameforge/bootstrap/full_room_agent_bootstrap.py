#!/usr/bin/env python3
"""Validated in-process CNS topology: room inventory, agent seats and bindings.

A materialized topology is not a running inference swarm. External services,
RAG and orchestration have separate qualification boundaries.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from threading import RLock
from typing import Any

_MAX_ROOMS = 2_000
_MAX_AGENTS = 16_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", re.ASCII)


def _identifier(value: Any, field: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


def _records(value: Any, cap: int, field: str) -> list[dict]:
    if type(value) is not list or len(value) > cap:
        raise ValueError(f"invalid or oversized {field}")
    if any(type(item) is not dict for item in value):
        raise ValueError(f"invalid {field} record")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class FullRoomAgentBootstrap:
    """Atomically publish a bounded, internally consistent topology.

    The authoritative registry supplies identifiers and default roles. Explicit
    assignments must reference actual rooms and unique available seats. Failed
    admission leaves the previously published topology unchanged.
    """

    def __init__(self):
        self._lock = RLock()
        self.rooms: list[dict[str, Any]] = []
        self.agents: list[dict[str, Any]] = []
        self.bindings: list[dict[str, Any]] = []
        self._generation = 0
        self._digest = _digest({"rooms": [], "agents": []})

    def bootstrap(self, rooms_manifest: list[dict], role_assignments: list[dict]) -> dict:
        with self._lock:
            rooms = self._instantiate_rooms(rooms_manifest)
            agents = self._spawn_agents(role_assignments, rooms)
            bindings = self._bind_agents(agents, rooms)
            receipt = _digest({"rooms": rooms, "agents": bindings})
            self.rooms = rooms
            self.agents = [dict(a) for a in bindings]
            self.bindings = [dict(a) for a in bindings]
            if receipt != self._digest:
                self._generation += 1
                self._digest = receipt
            return self._final_health_check()

    @staticmethod
    def _instantiate_rooms(manifest: list[dict]) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for r in _records(manifest, _MAX_ROOMS, "room manifest"):
            rid = _identifier(r.get("room_id") or r.get("id"), "room_id")
            if rid in seen:
                raise ValueError("duplicate room_id")
            seen.add(rid)
            seats = r.get("seats", 8)
            if type(seats) is not int or not 1 <= seats <= 64:
                raise ValueError("invalid room seat capacity")
            category = _identifier(r.get("category", "general"), "category")
            role = _identifier(r.get("role", "generalist"), "role")
            out.append({
                "room_id": rid, "category": category, "default_role": role,
                "status": "materialized", "seats": seats,
            })
        return sorted(out, key=lambda item: item["room_id"])

    @staticmethod
    def _spawn_agents(assignments: list[dict], rooms: list[dict]) -> list[dict]:
        values = _records(assignments, _MAX_AGENTS, "role assignments")
        by_room = {r["room_id"]: r for r in rooms}
        if not values:
            values = [
                {"agent_id": f"agent_{i:04d}", "room_id": room["room_id"],
                 "role_id": room["default_role"]}
                for i, room in enumerate(rooms)
            ]
        out = []
        seen: set[str] = set()
        for a in values:
            aid = _identifier(a.get("agent_id") or a.get("id"), "agent_id")
            if aid in seen:
                raise ValueError("duplicate agent_id")
            seen.add(aid)
            rid = _identifier(a.get("room_id"), "room_id")
            if rid not in by_room:
                raise ValueError("agent references unknown room")
            role = _identifier(a.get("role_id") or a.get("role") or by_room[rid]["default_role"], "role_id")
            seat = a.get("seat_id")
            if seat is not None:
                seat = _identifier(seat, "seat_id")
            out.append({
                "agent_id": aid, "room_id": rid, "role_id": role,
                "seat_id": seat, "status": "materialized",
            })
        return sorted(out, key=lambda item: item["agent_id"])

    @staticmethod
    def _bind_agents(agents: list[dict], rooms: list[dict]) -> list[dict]:
        capacity = {r["room_id"]: r["seats"] for r in rooms}
        reserved: dict[str, set[str]] = defaultdict(set)
        # Reserve explicit seats before automatic allocation, independent of
        # input order. A seat is identified in the room's real seat namespace.
        for a in agents:
            rid, seat = a["room_id"], a["seat_id"]
            if seat is None:
                continue
            allowed = {f"{rid}_seat_{i}" for i in range(capacity[rid])}
            if seat not in allowed or seat in reserved[rid]:
                raise ValueError("invalid or duplicate room seat")
            reserved[rid].add(seat)
        result = []
        for a in agents:
            rid, seat = a["room_id"], a["seat_id"]
            if seat is None:
                seat = next((
                    f"{rid}_seat_{i}" for i in range(capacity[rid])
                    if f"{rid}_seat_{i}" not in reserved[rid]
                ), None)
                if seat is None:
                    raise ValueError("room seat capacity exhausted")
                reserved[rid].add(seat)
            result.append({
                **a, "seat_id": seat, "bound": True, "room_status": "materialized",
            })
        return result

    def snapshot(self) -> dict:
        with self._lock:
            return {
                **self._final_health_check(),
                "room_inventory": [dict(r) for r in self.rooms],
                "agent_inventory": [dict(a) for a in self.agents],
            }

    def _final_health_check(self) -> dict:
        covered = {a["room_id"] for a in self.bindings}
        valid = bool(self.rooms and self.bindings)
        return {
            "rooms_instantiated": len(self.rooms),
            "agents_spawned": len(self.agents),
            "bindings": len(self.bindings),
            "unbound": sum(not a["bound"] for a in self.agents),
            "rooms_with_agents": len(covered),
            "rooms_without_agents": len(self.rooms) - len(covered),
            "generation": self._generation,
            "topology_sha256": self._digest,
            "coherence": "topology_validated" if valid else "unqualified",
            "synergy": "unqualified",
            "runtime_qualified": False,
            "overall_status": "TOPOLOGY_READY" if valid else "EMPTY_MANIFEST",
        }


if __name__ == "__main__":
    print(FullRoomAgentBootstrap().bootstrap(
        [{"room_id": "research", "category": "research"}],
        [{"agent_id": "a1", "role_id": "researcher", "room_id": "research"}],
    ))
