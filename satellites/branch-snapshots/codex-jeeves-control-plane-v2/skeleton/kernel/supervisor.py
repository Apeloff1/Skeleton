"""Kernel supervisor — liveness tracking and restart policy for agents.

Agents in the swarm die: exceptions escape, nodes partition, processes
get OOM-killed. The supervisor keeps a registry of supervised entities,
tracks their heartbeats, and applies a bounded-restart policy so a
crashed agent comes back fast — but a crash-looping agent is escalated
instead of flapping forever.

Design:

- :class:`HeartbeatMonitor` — sliding-window liveness; a node is
  SUSPECT after ``suspect_after`` seconds of silence, DEAD after
  ``dead_after``.
- :class:`RestartPolicy` — exponential backoff with a max-attempts
  ceiling; resets after a stability window.
- :class:`Supervisor` — ties liveness to restart decisions and emits
  lifecycle transitions the event bus can publish.

Pure logic, injectable clock, no threads.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class SupervisorError(KernelError):
    code = "KRN.SUPERVISOR"


class Health(str, Enum):
    ALIVE = "ALIVE"
    SUSPECT = "SUSPECT"
    DEAD = "DEAD"


class Lifecycle(str, Enum):
    STARTED = "STARTED"
    RESTARTING = "RESTARTING"
    ESCALATED = "ESCALATED"   # restart budget exhausted — human/other tier
    STOPPED = "STOPPED"


@dataclass
class RestartPolicy:
    max_attempts: int = 5
    base_backoff_s: float = 0.5
    max_backoff_s: float = 30.0
    stability_window_s: float = 60.0

    def backoff_for(self, attempt: int) -> float:
        """Exponential backoff, capped; attempt is 1-based."""
        return min(self.max_backoff_s, self.base_backoff_s * (2 ** (attempt - 1)))


@dataclass
class SupervisedNode:
    node_id: str
    policy: RestartPolicy
    last_heartbeat: float
    started_at: float
    attempts: int = 0
    last_restart_at: float = 0.0
    state: Lifecycle = Lifecycle.STARTED
    health: Health = Health.ALIVE


class HeartbeatMonitor:
    def __init__(self, suspect_after: float = 5.0, dead_after: float = 15.0) -> None:
        if not 0 < suspect_after < dead_after:
            raise SupervisorError(
                "liveness windows must satisfy 0 < suspect < dead",
                context={"suspect": suspect_after, "dead": dead_after},
            )
        self.suspect_after = suspect_after
        self.dead_after = dead_after

    def assess(self, silence_s: float) -> Health:
        if silence_s >= self.dead_after:
            return Health.DEAD
        if silence_s >= self.suspect_after:
            return Health.SUSPECT
        return Health.ALIVE


@dataclass(frozen=True)
class Transition:
    node_id: str
    from_health: Health
    to_health: Health
    action: Lifecycle
    backoff_s: float
    at: float


class Supervisor:
    """One supervisor per kernel instance; supervise() then heartbeat()/sweep()."""

    def __init__(
        self,
        *,
        suspect_after: float = 5.0,
        dead_after: float = 15.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.monitor = HeartbeatMonitor(suspect_after, dead_after)
        self._now = clock or time.monotonic
        self._nodes: Dict[str, SupervisedNode] = {}
        self._log: List[Transition] = []

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def supervise(self, node_id: str, policy: Optional[RestartPolicy] = None) -> None:
        if node_id in self._nodes:
            raise SupervisorError("node already supervised", context={"node": node_id})
        now = self._now()
        self._nodes[node_id] = SupervisedNode(
            node_id=node_id,
            policy=policy or RestartPolicy(),
            last_heartbeat=now,
            started_at=now,
        )

    def release(self, node_id: str) -> None:
        node = self._nodes.pop(node_id, None)
        if node is not None:
            node.state = Lifecycle.STOPPED

    def heartbeat(self, node_id: str) -> None:
        node = self._require(node_id)
        node.last_heartbeat = self._now()
        node.health = Health.ALIVE
        # A long quiet stretch of health resets the restart budget.
        if self._now() - node.last_restart_at > node.policy.stability_window_s:
            node.attempts = 0

    # ------------------------------------------------------------------
    # Sweep — call on a timer; returns transitions for the bus
    # ------------------------------------------------------------------

    def sweep(self) -> Tuple[Transition, ...]:
        now = self._now()
        out: List[Transition] = []
        for node in self._nodes.values():
            if node.state in (Lifecycle.ESCALATED, Lifecycle.STOPPED):
                continue
            new_health = self.monitor.assess(now - node.last_heartbeat)
            if new_health == node.health:
                continue
            transition = self._transition(node, new_health, now)
            out.append(transition)
            self._log.append(transition)
        return tuple(out)

    def _transition(self, node: SupervisedNode, new_health: Health, now: float) -> Transition:
        old = node.health
        node.health = new_health
        backoff = 0.0
        action = node.state
        if new_health == Health.DEAD:
            node.attempts += 1
            if node.attempts > node.policy.max_attempts:
                node.state = Lifecycle.ESCALATED
                action = Lifecycle.ESCALATED
            else:
                backoff = node.policy.backoff_for(node.attempts)
                node.last_restart_at = now
                node.state = Lifecycle.RESTARTING
                action = Lifecycle.RESTARTING
        elif new_health == Health.ALIVE:
            node.state = Lifecycle.STARTED
            action = Lifecycle.STARTED
        return Transition(node.node_id, old, new_health, action, backoff, now)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def status(self, node_id: str) -> Dict[str, object]:
        node = self._require(node_id)
        return {
            "node": node.node_id,
            "health": node.health.value,
            "state": node.state.value,
            "attempts": node.attempts,
            "silence_s": round(self._now() - node.last_heartbeat, 3),
        }

    def nodes(self) -> Tuple[str, ...]:
        return tuple(sorted(self._nodes))

    def transition_log(self) -> Tuple[Transition, ...]:
        return tuple(self._log)

    def _require(self, node_id: str) -> SupervisedNode:
        node = self._nodes.get(node_id)
        if node is None:
            raise SupervisorError("node not supervised", context={"node": node_id})
        return node
