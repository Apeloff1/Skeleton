"""Stigmergic coordination — pheromone-trail task routing for the swarm.

Ant colonies route foraging without a central planner: agents lay volatile
chemical trails on paths that paid off, trails evaporate, and the colony's
behaviour emerges from reinforcement + decay. This module gives the swarm the
same substrate, replacing central routing with **indirect coordination
through a shared environment**:

  - Successful task completions deposit pheromone on (capability → agent)
    trails, proportional to how well the task went.
  - Trails evaporate exponentially — stale routing preferences self-heal
    away, which makes the mesh adaptive to agent drift and failure without
    any explicit failure detection.
  - Route selection samples from the trail distribution (proportional
    exploration), so the swarm balances exploitation of proven agents with
    exploration of untried ones — the same explore/exploit balance ants get
    for free.

The trail field is the *only* shared state. No agent ever addresses another
directly; coordination is purely environmental. That is the definition of
stigmergy, and it is what makes the mesh robust when the scheduler dies.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import AgentId


@dataclass
class Trail:
    """One pheromone deposit on a (capability_key, agent) edge."""
    strength: float
    deposited_at: float = field(default_factory=time.time)
    deposits: int = 1


class PheromoneField:
    """
    The shared environment: a sparse field of volatile trails.

    Keys are ``(capability_key, agent_id)`` pairs. Reading the field always
    applies evaporation first, so readers see current effective strength.
    """

    def __init__(
        self,
        *,
        evaporation_rate: float = 0.01,   # per second
        saturation: float = 10.0,          # max effective trail strength
        bus: Optional[EventBus] = None,
    ) -> None:
        self._trails: Dict[Tuple[str, AgentId], Trail] = {}
        self.evaporation_rate = evaporation_rate
        self.saturation = saturation
        self._bus = bus

    # ------------------------------------------------------------------
    # Environment physics
    # ------------------------------------------------------------------

    def _effective(self, trail: Trail, now: Optional[float] = None) -> float:
        now = now or time.time()
        age = now - trail.deposited_at
        return trail.strength * math.exp(-self.evaporation_rate * age)

    def deposit(
        self,
        capability_key: str,
        agent_id: AgentId,
        amount: float,
        *,
        now: Optional[float] = None,
    ) -> float:
        """Reinforce a trail. Returns the new effective strength."""
        now = now or time.time()
        key = (capability_key, agent_id)
        existing = self._trails.get(key)
        base = self._effective(existing, now) if existing else 0.0
        new_strength = min(base + amount, self.saturation)
        self._trails[key] = Trail(
            strength=new_strength,
            deposited_at=now,
            deposits=(existing.deposits + 1) if existing else 1,
        )
        return new_strength

    def sense(self, capability_key: str) -> Dict[AgentId, float]:
        """Effective pheromone by agent for a capability, evaporation applied."""
        now = time.time()
        out: Dict[AgentId, float] = {}
        for (key, agent_id), trail in self._trails.items():
            if key != capability_key:
                continue
            strength = self._effective(trail, now)
            if strength > 1e-6:
                out[agent_id] = strength
        return out

    def prune(self, floor: float = 0.01) -> int:
        """Remove fully-evaporated trails. Returns count removed."""
        now = time.time()
        dead = [
            k for k, t in self._trails.items()
            if self._effective(t, now) < floor
        ]
        for k in dead:
            del self._trails[k]
        return len(dead)

    def stats(self) -> Dict[str, Any]:
        now = time.time()
        total = sum(self._effective(t, now) for t in self._trails.values())
        return {
            "trails": len(self._trails),
            "total_pheromone": round(total, 4),
            "evaporation_rate": self.evaporation_rate,
        }


class StigmergicRouter:
    """
    Routes tasks by sampling the pheromone field.

    Selection is proportional (roulette-wheel) over effective trail strength,
    with a uniform exploration floor so agents with no trail yet still get
    sampled — this is what keeps the colony from collapsing onto its first
    lucky agent.
    """

    def __init__(
        self,
        field: PheromoneField,
        *,
        exploration: float = 0.1,
        bus: Optional[EventBus] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.field = field
        self.exploration = exploration
        self._bus = bus
        self._rng = random.Random(seed)
        self._routed = 0

    def route(
        self,
        capability_key: str,
        candidates: List[AgentId],
    ) -> Optional[AgentId]:
        """Sample an agent from the trail distribution over candidates."""
        if not candidates:
            return None
        scents = self.field.sense(capability_key)
        floor = self.exploration
        weights = [scents.get(a, 0.0) + floor for a in candidates]
        total = sum(weights)
        pick = self._rng.random() * total
        acc = 0.0
        chosen = candidates[-1]
        for agent_id, w in zip(candidates, weights):
            acc += w
            if pick <= acc:
                chosen = agent_id
                break
        self._routed += 1
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="swarm.stigmergy.routed",
                    payload={
                        "capability": capability_key,
                        "agent": str(chosen),
                        "trail_strength": scents.get(chosen, 0.0),
                        "candidates": len(candidates),
                    },
                    correlation_id=f"stig_{self._routed}",
                )
            )
        return chosen

    def reinforce(
        self,
        capability_key: str,
        agent_id: AgentId,
        *,
        success: bool,
        quality: float = 1.0,
    ) -> float:
        """
        Feedback from the environment. Success deposits pheromone scaled by
        quality; failure deposits nothing (evaporation alone punishes it —
        negative evidence is free).
        """
        if not success:
            return self.field.sense(capability_key).get(agent_id, 0.0)
        return self.field.deposit(capability_key, agent_id, max(quality, 0.0))
