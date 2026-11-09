"""The agent mesh: discovery, routing, liveness, and quorum consensus.

The mesh maintains the live roster of agents. Each agent advertises
specialisations (capability names from the registry), carries a load metric,
and heartbeats. Routing selects the least-loaded healthy agent advertising a
capability, with deterministic tie-breaking (lexicographic id) so runs are
reproducible.

Liveness is TTL-based: agents whose last heartbeat is older than their TTL
are first quarantined (excluded from routing, still recoverable), then
evicted after a grace period. Both transitions emit domain events.

Consensus is a weighted simple-majority vote over named voters. A failed
quorum raises :class:`ConsensusError` with the full ballot attached as
context, so callers can inspect exactly who voted how.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from skeleton.kernel.errors import AgentNotFoundError, ConsensusError, NoCapableAgentError
from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import AgentId


class AgentLiveness(str, Enum):
    HEALTHY = "healthy"
    QUARANTINED = "quarantined"
    EVICTED = "evicted"


@dataclass
class Agent:
    """A live agent in the mesh."""

    agent_id: AgentId
    specialisations: frozenset[str]
    weight: float = 1.0
    load: float = 0.0  # 0.0 idle .. 1.0 saturated
    liveness: AgentLiveness = AgentLiveness.HEALTHY
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_ttl: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)
    completed_tasks: int = 0
    failed_tasks: int = 0

    def is_alive(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.last_heartbeat) <= self.heartbeat_ttl

    def grace_expired(self, now: float | None = None) -> bool:
        """True once the agent has been silent for 3x its TTL."""
        now = time.time() if now is None else now
        return (now - self.last_heartbeat) > self.heartbeat_ttl * 3

    def heartbeat(self, *, load: float | None = None) -> None:
        self.last_heartbeat = time.time()
        if load is not None:
            self.load = min(max(load, 0.0), 1.0)
        if self.liveness is AgentLiveness.QUARANTINED:
            self.liveness = AgentLiveness.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "specialisations": sorted(self.specialisations),
            "weight": self.weight,
            "load": round(self.load, 4),
            "liveness": self.liveness.value,
            "last_heartbeat": self.last_heartbeat,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class Ballot:
    """One voter's decision in a consensus round."""

    voter: AgentId
    approve: bool
    weight: float
    reason: str = ""


@dataclass(frozen=True)
class ConsensusResult:
    """Outcome of a quorum round."""

    proposal: str
    passed: bool
    approve_weight: float
    reject_weight: float
    total_weight: float
    ballots: tuple[Ballot, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal,
            "passed": self.passed,
            "approve_weight": self.approve_weight,
            "reject_weight": self.reject_weight,
            "total_weight": self.total_weight,
            "ballots": [
                {"voter": str(b.voter), "approve": b.approve, "weight": b.weight, "reason": b.reason}
                for b in self.ballots
            ],
        }


class AgentMesh:
    """Roster, routing, liveness, and consensus for the agent swarm."""

    def __init__(self, bus: EventBus | None = None, *, default_ttl: float = 30.0) -> None:
        self._agents: dict[AgentId, Agent] = {}
        self._bus = bus or EventBus()
        self._default_ttl = default_ttl

    # -- roster --------------------------------------------------------------

    def join(
        self,
        specialisations: set[str] | frozenset[str],
        *,
        agent_id: AgentId | None = None,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> Agent:
        """Register an agent with the mesh, emitting ``agent.mesh.joined``."""
        agent = Agent(
            agent_id=agent_id or AgentId.new(),
            specialisations=frozenset(specialisations),
            weight=weight,
            heartbeat_ttl=self._default_ttl,
            metadata=metadata or {},
        )
        self._agents[agent.agent_id] = agent
        self._bus.emit("agent.mesh.joined", {"agent": agent.to_dict()})
        return agent

    def leave(self, agent_id: AgentId) -> Agent:
        agent = self._agents.pop(agent_id, None)
        if agent is None:
            raise AgentNotFoundError(
                f"Agent {agent_id} is not in the mesh", context={"agent_id": str(agent_id)}
            )
        self._bus.emit("agent.mesh.left", {"agent_id": str(agent_id)})
        return agent

    def get(self, agent_id: AgentId) -> Agent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(
                f"Agent {agent_id} is not in the mesh", context={"agent_id": str(agent_id)}
            )
        return agent

    def roster(self, *, include_quarantined: bool = False) -> list[Agent]:
        agents = sorted(self._agents.values(), key=lambda a: str(a.agent_id))
        if not include_quarantined:
            agents = [a for a in agents if a.liveness is not AgentLiveness.QUARANTINED]
        return agents

    # -- routing -------------------------------------------------------------

    def candidates(self, capability: str) -> list[Agent]:
        """Healthy, alive agents advertising ``capability``, best first."""
        now = time.time()
        matches = [
            a
            for a in self._agents.values()
            if capability in a.specialisations
            and a.liveness is AgentLiveness.HEALTHY
            and a.is_alive(now)
        ]
        # Least-loaded first; deterministic tie-break on the id string.
        return sorted(matches, key=lambda a: (a.load, str(a.agent_id)))

    def route(self, capability: str) -> Agent:
        """Pick the single best agent for a capability or raise."""
        matches = self.candidates(capability)
        if not matches:
            raise NoCapableAgentError(
                f"No healthy agent advertises {capability!r}",
                context={
                    "capability": capability,
                    "roster_size": len(self._agents),
                    "advertised": sorted(
                        {s for a in self._agents.values() for s in a.specialisations}
                    ),
                },
            )
        chosen = matches[0]
        self._bus.emit(
            "agent.mesh.routed",
            {"capability": capability, "agent_id": str(chosen.agent_id), "load": chosen.load},
        )
        return chosen

    # -- liveness --------------------------------------------------------------

    def heartbeat(self, agent_id: AgentId, *, load: float | None = None) -> Agent:
        agent = self.get(agent_id)
        was_quarantined = agent.liveness is AgentLiveness.QUARANTINED
        agent.heartbeat(load=load)
        if was_quarantined:
            self._bus.emit("agent.mesh.recovered", {"agent_id": str(agent_id)})
        return agent

    def sweep(self, *, now: float | None = None) -> dict[str, list[str]]:
        """Quarantine silent agents; evict long-silent ones. Returns both lists."""
        now = time.time() if now is None else now
        quarantined: list[str] = []
        evicted: list[str] = []
        for agent in list(self._agents.values()):
            if agent.grace_expired(now):
                agent.liveness = AgentLiveness.EVICTED
                del self._agents[agent.agent_id]
                evicted.append(str(agent.agent_id))
                self._bus.emit("agent.mesh.evicted", {"agent_id": str(agent.agent_id)})
            elif not agent.is_alive(now) and agent.liveness is AgentLiveness.HEALTHY:
                agent.liveness = AgentLiveness.QUARANTINED
                quarantined.append(str(agent.agent_id))
                self._bus.emit("agent.mesh.quarantined", {"agent_id": str(agent.agent_id)})
        return {"quarantined": quarantined, "evicted": evicted}

    # -- consensus --------------------------------------------------------------

    def propose(
        self,
        proposal: str,
        *,
        voters: list[AgentId] | None = None,
        votes: dict[AgentId, tuple[bool, str]] | None = None,
        threshold: float = 0.5,
    ) -> ConsensusResult:
        """Run a weighted simple-majority vote.

        ``votes`` maps voter -> (approve, reason). Voters not in ``votes``
        abstain (their weight counts toward the denominator, which is the
        conservative choice: a quorum of silence fails the proposal).
        """
        voter_ids = voters if voters is not None else [a.agent_id for a in self.roster()]
        if not voter_ids:
            raise ConsensusError(
                "No voters available for consensus",
                context={"proposal": proposal},
            )
        ballots: list[Ballot] = []
        approve_weight = reject_weight = total_weight = 0.0
        for voter_id in voter_ids:
            agent = self._agents.get(voter_id)
            if agent is None:
                continue  # unknown voters cannot ballot
            total_weight += agent.weight
            approve, reason = (True, "default yes") if votes is None else votes.get(voter_id, (False, "abstain"))
            ballots.append(Ballot(voter=voter_id, approve=approve, weight=agent.weight, reason=reason))
            if approve:
                approve_weight += agent.weight
            else:
                reject_weight += agent.weight
        passed = total_weight > 0 and (approve_weight / total_weight) > threshold
        result = ConsensusResult(
            proposal=proposal,
            passed=passed,
            approve_weight=approve_weight,
            reject_weight=reject_weight,
            total_weight=total_weight,
            ballots=tuple(ballots),
        )
        self._bus.emit("agent.mesh.consensus", result.to_dict())
        if not passed:
            raise ConsensusError(
                f"Proposal {proposal!r} failed quorum "
                f"({approve_weight:.2f}/{total_weight:.2f} approve weight)",
                context=result.to_dict(),
            )
        return result

    # -- introspection ---------------------------------------------------------

    def advertised_capabilities(self) -> list[str]:
        return sorted({s for a in self._agents.values() for s in a.specialisations})

    def stats(self) -> dict[str, Any]:
        by_liveness: dict[str, int] = {}
        for agent in self._agents.values():
            by_liveness[agent.liveness.value] = by_liveness.get(agent.liveness.value, 0) + 1
        return {
            "agents": len(self._agents),
            "by_liveness": by_liveness,
            "advertised_capabilities": self.advertised_capabilities(),
            "mean_load": (
                round(sum(a.load for a in self._agents.values()) / len(self._agents), 4)
                if self._agents
                else 0.0
            ),
        }
