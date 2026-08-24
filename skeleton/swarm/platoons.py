"""Platoons — specialised agent squads with role-level doctrine.

The swarm charter names four roles — Scout, Worker, Guardian, Oracle —
but the mesh treats every agent identically. Platoons give each role its
own squad with its own operating doctrine: how many agents it needs, how
it votes internally before answering the mesh, and when it escalates.

  - **ScoutPlatoon** — fans out, returns the union of findings; votes
    rarely, speed over consensus.
  - **WorkerPlatoon** — capacity-pooled task execution; load-balances by
    effective capacity, escalates when saturated.
  - **GuardianPlatoon** — quorum-gated: it answers only when a strict
    majority of its agents agree, because a split guardian vote is itself
    a security signal.
  - **OraclePlatoon** — aggregates estimates through the hive module and
    reports the diversity score alongside the answer.

Each platoon is a thin doctrine layer over the existing AgentState list;
the mesh routes to a platoon, the platoon applies its doctrine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Sequence

from skeleton.kernel.events import DomainEvent, EventBus
from .hive import Estimate, HiveMind
from .types import AgentState, AgentRole, AgentStatus


class Doctrine(Enum):
    FAN_OUT = auto()       # scouts: union of everything
    POOLED = auto()        # workers: balance by capacity
    QUORUM = auto()        # guardians: majority must agree
    AGGREGATED = auto()    # oracles: hive aggregation


@dataclass
class PlatoonReport:
    role: str
    agents_available: int
    doctrine: str
    result: Any
    escalated: bool = False


class Platoon:
    """Base: a role-filtered squad with a doctrine."""

    MIN_SQUAD = 2

    def __init__(self, role: AgentRole, doctrine: Doctrine,
                 *, bus: Optional[EventBus] = None) -> None:
        self.role = role
        self.doctrine = doctrine
        self._bus = bus
        self._missions = 0

    def available(self, agents: Sequence[AgentState]) -> List[AgentState]:
        return [a for a in agents
                if a.role == self.role
                and a.is_alive()
                and a.status not in (AgentStatus.QUARANTINED, AgentStatus.FAILED)]

    def execute(self, agents: Sequence[AgentState], task: Any,
                fn: Callable[[AgentState, Any], Any]) -> PlatoonReport:
        squad = self.available(agents)
        if len(squad) < self.MIN_SQUAD:
            return PlatoonReport(
                role=self.role.name, agents_available=len(squad),
                doctrine=self.doctrine.name, result=None, escalated=True,
            )
        self._missions += 1
        result = self._apply_doctrine(squad, task, fn)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="swarm.platoon.mission",
                    payload={"role": self.role.name, "doctrine": self.doctrine.name,
                             "squad": len(squad), "mission": self._missions},
                    correlation_id=f"plt_{self.role.name}_{self._missions}",
                )
            )
        return PlatoonReport(role=self.role.name, agents_available=len(squad),
                             doctrine=self.doctrine.name, result=result)

    def _apply_doctrine(self, squad, task, fn):
        if self.doctrine == Doctrine.FAN_OUT:
            out: List[Any] = []
            for agent in squad:
                r = fn(agent, task)
                out.extend(r if isinstance(r, list) else [r])
            return out
        if self.doctrine == Doctrine.POOLED:
            # assign to the least-loaded agent (highest effective capacity)
            best = max(squad, key=lambda a: a.effective_capacity())
            return fn(best, task)
        if self.doctrine == Doctrine.QUORUM:
            votes: Dict[str, int] = {}
            for agent in squad:
                verdict = repr(fn(agent, task))
                votes[verdict] = votes.get(verdict, 0) + 1
            winner, count = max(votes.items(), key=lambda kv: kv[1])
            if count * 2 <= len(squad):
                return PlatoonReport(role=self.role.name, agents_available=len(squad),
                                     doctrine=self.doctrine.name, result=None,
                                     escalated=True)
            return winner
        return None


class OraclePlatoon(Platoon):
    """Doctrine is aggregation; it lives here because it needs the hive."""

    def __init__(self, hive: Optional[HiveMind] = None,
                 *, bus: Optional[EventBus] = None) -> None:
        super().__init__(AgentRole.ORACLE, Doctrine.AGGREGATED, bus=bus)
        self._hive = hive or HiveMind(bus=bus)

    def estimate(self, agents: Sequence[AgentState],
                 estimates: Sequence[Estimate]):
        squad = self.available(agents)
        if len(squad) < self.MIN_SQUAD:
            return PlatoonReport(role=self.role.name, agents_available=len(squad),
                                 doctrine=self.doctrine.name, result=None,
                                 escalated=True)
        weights = {str(a.agent_id): a.reputation * a.capabilities.prediction
                   for a in squad}
        result = self._hive.aggregate(
            estimates, method="trimmed_weighted",
            weight_of=lambda aid: weights.get(aid, 0.0) or None,
        )
        return PlatoonReport(role=self.role.name, agents_available=len(squad),
                             doctrine=self.doctrine.name, result=result)


def standard_platoons(*, bus: Optional[EventBus] = None) -> Dict[str, Platoon]:
    """The four charter platoons, ready to register with the mesh."""
    return {
        "scout": Platoon(AgentRole.SCOUT, Doctrine.FAN_OUT, bus=bus),
        "worker": Platoon(AgentRole.WORKER, Doctrine.POOLED, bus=bus),
        "guardian": Platoon(AgentRole.GUARDIAN, Doctrine.QUORUM, bus=bus),
        "oracle": OraclePlatoon(bus=bus),
    }
