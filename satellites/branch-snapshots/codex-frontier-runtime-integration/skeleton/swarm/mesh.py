"""
Skeleton Swarm — Multi-agent mesh with negotiation and stigmergy

Provides:
- SwarmMesh: Route tasks to capable agents
- PheromoneField: Stigmergic communication layer
- HiveMind: Collective reasoning and consensus
- CapabilityNegotiator: Dynamic capability discovery
- Platoons: Pre-configured agent groups
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class Agent:
    """A single agent in the swarm."""
    agent_id: str
    specialisations: Set[str]
    weight: float = 1.0
    load: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)

    def is_alive(self) -> bool:
        return time.time() - self.last_seen < 60.0  # 60s heartbeat timeout

    def score(self, capability: str) -> float:
        """Score how well this agent matches a capability request."""
        if capability not in self.specialisations:
            return 0.0
        return (self.weight / (1.0 + self.load)) if self.is_alive() else 0.0


class SwarmMesh:
    """Route tasks to the most capable agents in the swarm."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._agents: Dict[str, Agent] = {}
        self._bus = bus
        self._stats = {"routed": 0, "registered": 0, "failed": 0}

    def join(self, specialisations: Set[str], weight: float = 1.0, metadata: Optional[Dict[str, Any]] = None) -> Agent:
        """Register a new agent in the swarm."""
        agent = Agent(
            agent_id=str(uuid.uuid4())[:8],
            specialisations=set(specialisations),
            weight=weight,
            metadata=metadata or {},
        )
        self._agents[agent.agent_id] = agent
        self._stats["registered"] += 1
        
        if self._bus:
            self._bus.emit("swarm.agent.joined", {
                "agent_id": agent.agent_id,
                "specialisations": list(specialisations),
            })
        
        return agent

    def route(self, capability: str) -> Optional[Agent]:
        """Find the best agent for a given capability."""
        candidates = [(a.score(capability), a) for a in self._agents.values()]
        candidates = [(s, a) for s, a in candidates if s > 0]
        
        if not candidates:
            self._stats["failed"] += 1
            return None
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        best.load += 1.0
        best.last_seen = time.time()
        self._stats["routed"] += 1
        
        if self._bus:
            self._bus.emit("swarm.task.routed", {
                "capability": capability,
                "agent_id": best.agent_id,
            })
        
        return best

    def heartbeat(self, agent_id: str) -> None:
        """Update agent heartbeat."""
        if agent_id in self._agents:
            self._agents[agent_id].last_seen = time.time()

    def stats(self) -> Dict[str, Any]:
        alive = sum(1 for a in self._agents.values() if a.is_alive())
        return {
            "agents": len(self._agents),
            "alive": alive,
            **self._stats,
        }


class PheromoneField:
    """Stigmergic communication via evaporating pheromone trails."""

    def __init__(self, bus: Optional[EventBus] = None, decay_rate: float = 0.95):
        self._trails: Dict[str, Dict[str, float]] = {}  # location -> {marker: strength}
        self._decay_rate = decay_rate
        self._bus = bus

    def deposit(self, location: str, marker: str, strength: float = 1.0) -> None:
        """Deposit a pheromone marker at a location."""
        self._trails.setdefault(location, {})[marker] = self._trails.get(location, {}).get(marker, 0) + strength
        if self._bus:
            self._bus.emit("swarm.pheromone.deposited", {"location": location, "marker": marker, "strength": strength})

    def sense(self, location: str, marker: Optional[str] = None) -> Dict[str, float]:
        """Sense pheromones at a location."""
        trails = self._trails.get(location, {})
        if marker:
            return {marker: trails.get(marker, 0)}
        return dict(trails)

    def evaporate(self) -> None:
        """Decay all pheromone trails."""
        for location in list(self._trails.keys()):
            for marker in list(self._trails[location].keys()):
                self._trails[location][marker] *= self._decay_rate
                if self._trails[location][marker] < 0.01:
                    del self._trails[location][marker]
            if not self._trails[location]:
                del self._trails[location]

    def stats(self) -> Dict[str, Any]:
        total_markers = sum(len(t) for t in self._trails.values())
        return {"locations": len(self._trails), "markers": total_markers, "decay": self._decay_rate}


class StigmergicRouter:
    """Route decisions influenced by pheromone trails."""

    def __init__(self, field: PheromoneField, bus: Optional[EventBus] = None, seed: Optional[int] = None):
        self._field = field
        self._bus = bus
        self._rng = __import__('random').Random(seed)

    def route_with_stigmergy(self, mesh: SwarmMesh, capability: str, location: str = "default") -> Optional[Agent]:
        """Route considering both agent scores and local pheromone signals."""
        # Get base agent candidates
        candidates = [(a.score(capability), a) for a in mesh._agents.values()]
        candidates = [(s, a) for s, a in candidates if s > 0]
        
        if not candidates:
            return None
        
        # Boost scores based on positive pheromones at location
        pheromones = self._field.sense(location)
        boosted = []
        for score, agent in candidates:
            boost = sum(pheromones.get(spec, 0) for spec in agent.specialisations) * 0.1
            boosted.append((score + boost, agent))
        
        boosted.sort(key=lambda x: x[0], reverse=True)
        return boosted[0][1]


class HiveMind:
    """Collective reasoning and consensus formation."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._opinions: Dict[str, List[Dict[str, Any]]] = {}  # topic -> [{agent_id, value, confidence}]
        self._bus = bus

    def contribute(self, topic: str, agent_id: str, value: Any, confidence: float = 1.0) -> None:
        """Contribute an opinion to a topic."""
        self._opinions.setdefault(topic, []).append({
            "agent_id": agent_id,
            "value": value,
            "confidence": confidence,
            "timestamp": time.time(),
        })

    def consensus(self, topic: str, threshold: float = 0.6) -> Optional[Any]:
        """Attempt to reach consensus on a topic."""
        opinions = self._opinions.get(topic, [])
        if not opinions:
            return None
        
        # Weighted voting for scalar values
        try:
            values = [o["value"] for o in opinions if isinstance(o["value"], (int, float))]
            if values:
                weights = [o["confidence"] for o in opinions if isinstance(o["value"], (int, float))]
                weighted_sum = sum(v * w for v, w in zip(values, weights))
                total_weight = sum(weights)
                return weighted_sum / total_weight if total_weight > 0 else None
        except (TypeError, ValueError):
            pass
        
        # Majority vote for categorical
        from collections import Counter
        votes = Counter(str(o["value"]) for o in opinions)
        most_common, count = votes.most_common(1)[0]
        if count / len(opinions) >= threshold:
            return most_common
        
        return None  # No consensus

    def stats(self) -> Dict[str, Any]:
        return {"topics": len(self._opinions), "total_opinions": sum(len(o) for o in self._opinions.values())}


class CapabilityNegotiator:
    """Dynamic capability discovery and negotiation."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._capabilities: Dict[str, Set[str]] = {}  # capability -> {agent_ids}
        self._bus = bus

    def advertise(self, agent_id: str, capabilities: Set[str]) -> None:
        """Advertise capabilities for an agent."""
        for cap in capabilities:
            self._capabilities.setdefault(cap, set()).add(agent_id)

    def discover(self, capability: str) -> Set[str]:
        """Discover agents that provide a capability."""
        return set(self._capabilities.get(capability, set()))

    def negotiate(self, agent_id: str, required: Set[str]) -> Dict[str, Any]:
        """Negotiate which capabilities an agent can fulfill."""
        available = set()
        missing = set()
        for cap in required:
            if agent_id in self._capabilities.get(cap, set()):
                available.add(cap)
            else:
                missing.add(cap)
        return {"available": available, "missing": missing, "can_fulfill": len(missing) == 0}


class Platoons:
    """Pre-configured agent groups for common tasks."""

    TEMPLATES = {
        "scout": {"specialisations": {"explore", "sense"}, "count": 3},
        "worker": {"specialisations": {"process", "transform"}, "count": 5},
        "guard": {"specialisations": {"protect", "monitor"}, "count": 2},
        "council": {"specialisations": {"reason", "decide"}, "count": 7},
    }

    def __init__(self, bus: Optional[EventBus] = None):
        self._platoons: Dict[str, List[Agent]] = {}
        self._bus = bus

    def deploy(self, mesh: SwarmMesh, template: str, count: Optional[int] = None) -> List[Agent]:
        """Deploy a platoon from a template."""
        spec = self.TEMPLATES.get(template, {"specialisations": {"general"}, "count": 1})
        n = count or spec["count"]
        
        agents = []
        for _ in range(n):
            agent = mesh.join(spec["specialisations"])
            agents.append(agent)
        
        self._platoons[template] = agents
        
        if self._bus:
            self._bus.emit("swarm.platoon.deployed", {
                "template": template,
                "count": len(agents),
            })
        
        return agents

    def stats(self) -> Dict[str, Any]:
        return {name: len(agents) for name, agents in self._platoons.items()}


def standard_platoons(bus: Optional[EventBus] = None) -> Platoons:
    """Factory for standard platoon configurations."""
    return Platoons(bus=bus)
