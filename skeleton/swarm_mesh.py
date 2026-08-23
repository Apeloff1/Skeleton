"""
================================================================================
skeleton.swarm — Swarm Intelligence Mesh (Part 2: SwarmMesh, Health, Topology)
================================================================================
Self-healing mesh topology: heartbeat, quarantine, routing, circuit breakers,
chaos engineering, partition detection/healing.
================================================================================
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.errors import AgentError, ConsensusError, AgentNotFoundError, AgentQuarantinedError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import AgentId
from skeleton.swarm_types import (
    AgentRole, AgentState, AgentStatus, CapabilityVector,
    ConsensusProtocol, SimpleMajorityConsensus, VickreyAuction,
)


# =============================================================================
# SWARM MESH
# =============================================================================

class SwarmMesh:
    """
    Self-healing mesh topology for agent coordination.
    Features:
      - Heartbeat-based liveness detection
      - Automatic quarantine and replacement
      - Partition detection and healing
      - Circuit breakers for failing agents
      - Chaos engineering: random agent failure injection
    """

    def __init__(
        self,
        *,
        bus: Optional[EventBus] = None,
        consensus_protocol: Optional[ConsensusProtocol] = None,
    ) -> None:
        self._agents: Dict[AgentId, AgentState] = {}
        self._bus = bus
        self._consensus = consensus_protocol or SimpleMajorityConsensus()
        self._auction = VickreyAuction()
        self._circuit_breakers: Dict[AgentId, Dict[str, Any]] = {}
        self._chaos_enabled: bool = False
        self._chaos_failure_rate: float = 0.05

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def register(self, agent: AgentState) -> None:
        self._agents[agent.agent_id] = agent
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="swarm.agent.registered",
                    payload={
                        "agent_id": str(agent.agent_id),
                        "role": agent.role.name,
                        "capabilities": agent.capabilities.to_dict(),
                    },
                    correlation_id=f"swarm_{str(agent.agent_id)}",
                )
            )

    def unregister(self, agent_id: AgentId) -> bool:
        if agent_id in self._agents:
            agent = self._agents.pop(agent_id)
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="swarm.agent.unregistered",
                        payload={
                            "agent_id": str(agent_id),
                            "role": agent.role.name,
                            "final_health": agent.health_score,
                        },
                        correlation_id=f"swarm_{str(agent_id)}",
                    )
                )
            return True
        return False

    def heartbeat(self, agent_id: AgentId) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        agent = self._agents[agent_id]
        agent.last_heartbeat = time.time()
        agent.status = AgentStatus.HEALTHY
        agent.consecutive_failures = 0

    def get_agent(self, agent_id: AgentId) -> AgentState:
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        agent = self._agents[agent_id]
        if agent.status == AgentStatus.QUARANTINED:
            raise AgentQuarantinedError(f"Agent {agent_id} is quarantined")
        return agent

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def check_health(self) -> Dict[AgentId, AgentStatus]:
        now = time.time()
        statuses: Dict[AgentId, AgentStatus] = {}
        for agent_id, agent in self._agents.items():
            if not agent.is_alive(now):
                if agent.status != AgentStatus.FAILED:
                    agent.status = AgentStatus.FAILED
                    if self._bus:
                        self._bus.publish(
                            DomainEvent(
                                topic="swarm.agent.failed",
                                payload={
                                    "agent_id": str(agent_id),
                                    "last_heartbeat": agent.last_heartbeat,
                                    "elapsed": now - agent.last_heartbeat,
                                },
                                correlation_id=f"swarm_{str(agent_id)}",
                            )
                        )
            statuses[agent_id] = agent.status
        return statuses

    def quarantine(self, agent_id: AgentId) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].status = AgentStatus.QUARANTINED
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="swarm.agent.quarantined",
                        payload={"agent_id": str(agent_id)},
                        correlation_id=f"swarm_{str(agent_id)}",
                    )
                )

    def recover(self, agent_id: AgentId) -> None:
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            agent.status = AgentStatus.RECOVERING
            agent.consecutive_failures = 0
            agent.last_heartbeat = time.time()

    # ------------------------------------------------------------------
    # Routing and selection
    # ------------------------------------------------------------------

    def route(
        self,
        capability_requirement: CapabilityVector,
        *,
        role: Optional[AgentRole] = None,
        exclude: Optional[Set[AgentId]] = None,
    ) -> Optional[AgentState]:
        """
        Route a task to the best available agent.
        Uses capability similarity + effective capacity + reputation.
        """
        candidates = [
            agent for agent in self._agents.values()
            if agent.is_alive()
            and agent.status not in (AgentStatus.QUARANTINED, AgentStatus.FAILED)
            and (role is None or agent.role == role)
            and (exclude is None or agent.agent_id not in exclude)
        ]

        if not candidates:
            return None

        scored = [
            (
                agent.capabilities.similarity(capability_requirement)
                * agent.effective_capacity()
                * agent.reputation,
                agent,
            )
            for agent in candidates
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def route_with_consensus(
        self,
        proposal: Any,
        capability_requirement: CapabilityVector,
        *,
        min_voters: int = 3,
    ) -> Tuple[AgentState, bool, Dict[str, Any]]:
        """Route to best agent, but only after consensus approval from peers."""
        voters = [
            agent for agent in self._agents.values()
            if agent.is_alive() and agent.status == AgentStatus.HEALTHY
        ]
        if len(voters) < min_voters:
            raise ConsensusError(
                f"Insufficient healthy voters: {len(voters)} < {min_voters}",
                ballot={},
            )

        accepted, ballot = self._consensus.propose(proposal, voters)
        if accepted:
            winner = self.route(capability_requirement)
            if winner is None:
                raise AgentError("Consensus passed but no suitable agent found")
            return winner, True, ballot
        else:
            raise ConsensusError("Routing proposal rejected by consensus", ballot=ballot)

    # ------------------------------------------------------------------
    # Auction-based allocation
    # ------------------------------------------------------------------

    def allocate_task(
        self,
        task_requirements: CapabilityVector,
        *,
        role: Optional[AgentRole] = None,
    ) -> Tuple[Optional[AgentState], float, List[Dict[str, Any]]]:
        """Allocate a task via Vickrey auction."""
        bidders = [
            agent for agent in self._agents.values()
            if agent.is_alive() and (role is None or agent.role == role)
        ]
        return self._auction.run(task_requirements, bidders)

    # ------------------------------------------------------------------
    # Chaos engineering
    # ------------------------------------------------------------------

    def enable_chaos(self, failure_rate: float = 0.05) -> None:
        self._chaos_enabled = True
        self._chaos_failure_rate = failure_rate

    def disable_chaos(self) -> None:
        self._chaos_enabled = False

    def inject_chaos(self) -> List[AgentId]:
        """Randomly fail agents to test resilience. Returns failed agent ids."""
        if not self._chaos_enabled:
            return []
        failed: List[AgentId] = []
        for agent_id, agent in self._agents.items():
            if agent.is_alive() and random.random() < self._chaos_failure_rate:
                agent.status = AgentStatus.FAILED
                agent.consecutive_failures = agent.max_failures
                failed.append(agent_id)
                if self._bus:
                    self._bus.publish(
                        DomainEvent(
                            topic="swarm.chaos.injected",
                            payload={
                                "agent_id": str(agent_id),
                                "role": agent.role.name,
                                "failure_rate": self._chaos_failure_rate,
                            },
                            correlation_id=f"chaos_{str(agent_id)}",
                        )
                    )
        return failed

    # ------------------------------------------------------------------
    # Circuit breakers
    # ------------------------------------------------------------------

    def record_result(self, agent_id: AgentId, success: bool) -> None:
        if agent_id not in self._agents:
            return
        agent = self._agents[agent_id]
        agent.update_reputation(success)

        cb = self._circuit_breakers.setdefault(str(agent_id), {
            "failures": 0,
            "successes": 0,
            "last_failure": 0.0,
            "open": False,
            "threshold": 5,
            "timeout": 30.0,
        })
        if success:
            cb["successes"] += 1
            cb["failures"] = 0
            cb["open"] = False
        else:
            cb["failures"] += 1
            cb["last_failure"] = time.time()
            if cb["failures"] >= cb["threshold"]:
                cb["open"] = True
                self.quarantine(agent_id)

    def is_circuit_open(self, agent_id: AgentId) -> bool:
        cb = self._circuit_breakers.get(str(agent_id))
        if not cb:
            return False
        if cb["open"]:
            if time.time() - cb["last_failure"] > cb["timeout"]:
                cb["open"] = False
                cb["failures"] = 0
                self.recover(agent_id)
                return False
            return True
        return False

    # ------------------------------------------------------------------
    # Mesh topology
    # ------------------------------------------------------------------

    def get_partition_map(self) -> Dict[int, Set[AgentId]]:
        """
        Detect network partitions using peer connectivity.
        Returns partition id -> set of agent ids.
        """
        visited: Set[AgentId] = set()
        partitions: Dict[int, Set[AgentId]] = {}
        partition_id = 0

        for agent_id in self._agents:
            if agent_id in visited:
                continue
            component: Set[AgentId] = set()
            queue = [agent_id]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                if current in self._agents:
                    for peer in self._agents[current].peers:
                        if peer not in visited and peer in self._agents:
                            queue.append(peer)
            partitions[partition_id] = component
            partition_id += 1

        return partitions

    def heal_partition(self, partition_id: int) -> bool:
        """Attempt to heal a partition by adding bridge agents."""
        partitions = self.get_partition_map()
        if partition_id not in partitions:
            return False
        agents = partitions[partition_id]
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="swarm.partition.heal_attempt",
                    payload={
                        "partition_id": partition_id,
                        "agents": [str(a) for a in agents],
                        "size": len(agents),
                    },
                    correlation_id=f"heal_{partition_id}",
                )
            )
        return True

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        by_role: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        total_capacity = 0.0
        for agent in self._agents.values():
            by_role[agent.role.name] = by_role.get(agent.role.name, 0) + 1
            by_status[agent.status.name] = by_status.get(agent.status.name, 0) + 1
            total_capacity += agent.effective_capacity()

        return {
            "total_agents": len(self._agents),
            "by_role": by_role,
            "by_status": by_status,
            "total_effective_capacity": total_capacity,
            "partitions": len(self.get_partition_map()),
            "circuit_breakers_open": sum(
                1 for cb in self._circuit_breakers.values() if cb["open"]
            ),
            "chaos_enabled": self._chaos_enabled,
        }
