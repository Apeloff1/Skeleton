"""Agent heartbeat registry — liveness with TTL sweeps.

The mesh decides scheduling; liveness is decided here. Agents beat into
the registry; a sweep demotes agents whose TTL expired. AgentSettings
already declares ``heartbeat_ttl_seconds`` — this enforces it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from skeleton.kernel.errors import AgentError


class HeartbeatError(AgentError):
    code = "AGT.HEARTBEAT"


@dataclass
class HeartbeatRecord:
    agent_id: str
    last_beat: float
    ttl_s: float
    alive: bool = True


class HeartbeatRegistry:
    """Tracks beats; sweep() flips expired agents to dead."""

    def __init__(self, *, ttl_s: float = 30.0, clock: Optional[Callable[[], float]] = None) -> None:
        if ttl_s <= 0:
            raise HeartbeatError("ttl must be positive")
        self.ttl_s = ttl_s
        self._now = clock or time.monotonic
        self._records: Dict[str, HeartbeatRecord] = {}

    def register(self, agent_id: str) -> None:
        self._records[agent_id] = HeartbeatRecord(
            agent_id=agent_id, last_beat=self._now(), ttl_s=self.ttl_s
        )

    def beat(self, agent_id: str) -> None:
        record = self._records.get(agent_id)
        if record is None:
            raise HeartbeatError("unregistered agent", context={"agent": agent_id})
        record.last_beat = self._now()
        record.alive = True

    def sweep(self) -> Tuple[str, ...]:
        now = self._now()
        expired: list = []
        for record in self._records.values():
            if record.alive and now - record.last_beat > record.ttl_s:
                record.alive = False
                expired.append(record.agent_id)
        return tuple(expired)

    def is_alive(self, agent_id: str) -> bool:
        record = self._records.get(agent_id)
        return record.alive if record else False

    def live_agents(self) -> Tuple[str, ...]:
        return tuple(a for a, r in self._records.items() if r.alive)
