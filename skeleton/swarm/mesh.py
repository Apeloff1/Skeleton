"""Swarm mesh contracts.

GB-29's bounded handoff :class:`Mesh` is the current canonical mesh surface.
The legacy routing classes remain compatibility exports because Genesis,
negotiation/platoon/stigmergy shims, and public regression contracts still
consume them. New code should prefer the focused GB-29 and AgentMesh APIs.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from skeleton.kernel.events import EventBus
from skeleton.swarm.law import N_CAP


class Mesh:
    def __init__(self) -> None:
        self.offers: dict[str, str] = {}
        self.accepted: list[tuple[str, str]] = []
        self.refused: list[str] = []
        self.expired: list[str] = []

    def offer(self, agent: str, task: str) -> str:
        if len(self.offers) >= N_CAP:
            raise ValueError("n-cap")
        self.offers[agent] = task
        return "offer"

    def accept(self, agent: str, peer: str) -> str:
        if agent not in self.offers:
            return "refuse"
        self.offers.pop(agent)
        self.accepted.append((agent, peer))
        return "accept"

    def refuse(self, agent: str) -> str:
        self.refused.append(agent)
        self.offers.pop(agent, None)
        return "refuse"

    def expire(self, agent: str) -> str:
        self.expired.append(agent)
        self.offers.pop(agent, None)
        return "expire"

    def handoff(self, a: str, b: str, task: str) -> dict:
        self.offer(a, task)
        state = self.accept(a, b)
        return {
            "kind": "handoff",
            "state": state,
            "from": a,
            "to": b,
            "task": task,
            "stored_prose": 0,
        }


# Compatibility surface -----------------------------------------------------
#
# These types predate GB-29 and are intentionally kept until all live callers
# have migrated. Keeping them here makes the refactor additive instead of
# breaking Genesis and the package's documented public API.

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
        if len(self._agents) >= N_CAP:
            raise ValueError("n-cap")
        if not isinstance(specialisations, set) or not specialisations or any(not isinstance(item, str) or not item for item in specialisations):
            raise ValueError("specialisations must be a non-empty set of names")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not weight > 0:
            raise ValueError("weight must be positive")
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

    def agents(self) -> tuple[Agent, ...]:
        return tuple(self._agents.values())

    def route(self, capability: str) -> Optional[Agent]:
        """Find the best agent for a given capability."""
        candidates = [(a.score(capability), a) for a in self.agents()]
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
        if isinstance(decay_rate, bool) or not isinstance(decay_rate, (int, float)) or not 0.0 < float(decay_rate) <= 1.0:
            raise ValueError("decay_rate must be in (0, 1]")
        self._trails: Dict[str, Dict[str, float]] = {}  # location -> {marker: strength}
        self._decay_rate = float(decay_rate)
        self._bus = bus

    def deposit(self, location: str, marker: str, strength: float = 1.0) -> None:
        """Deposit a pheromone marker at a location."""
        if not isinstance(location, str) or not location.strip() or not isinstance(marker, str) or not marker.strip():
            raise ValueError("location and marker are required")
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not strength > 0:
            raise ValueError("strength must be positive")
        trails = self._trails.setdefault(location, {})
        trails[marker] = min(100.0, trails.get(marker, 0.0) + float(strength))
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
        candidates = [(a.score(capability), a) for a in mesh.agents()]
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
        if not isinstance(topic, str) or not topic.strip() or not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("topic and agent_id are required")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0.0 < float(confidence) <= 1.0:
            raise ValueError("confidence must be in (0, 1]")
        opinions = self._opinions.setdefault(topic, [])
        opinions[:] = [item for item in opinions if item["agent_id"] != agent_id]
        opinions.append({
            "agent_id": agent_id,
            "value": value,
            "confidence": float(confidence),
            "timestamp": time.time(),
        })

    def consensus(self, topic: str, threshold: float = 0.6) -> Optional[Any]:
        """Return a value only when enough weight actually agrees."""
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.0 < float(threshold) <= 1.0:
            raise ValueError("threshold must be in (0, 1]")
        opinions = self._opinions.get(topic, [])
        if not opinions:
            return None
        total = sum(item["confidence"] for item in opinions)
        if total <= 0:
            return None
        numeric = [item for item in opinions if not isinstance(item["value"], bool) and isinstance(item["value"], (int, float))]
        if len(numeric) == len(opinions):
            ordered = sorted(float(item["value"]) for item in numeric)
            median = ordered[len(ordered) // 2]
            spread = max(ordered) - min(ordered)
            scale = max(1.0, abs(median))
            if spread > 0.05 * scale:
                return None
            return sum(float(item["value"]) * item["confidence"] for item in numeric) / total
        votes: Dict[str, float] = {}
        for item in opinions:
            key = str(item["value"])
            votes[key] = votes.get(key, 0.0) + item["confidence"]
        choice, weight = max(votes.items(), key=lambda item: item[1])
        if weight / total >= float(threshold):
            return choice
        return None

    def stats(self) -> Dict[str, Any]:
        return {"topics": len(self._opinions), "total_opinions": sum(len(o) for o in self._opinions.values())}


class CapabilityNegotiator:
    """Dynamic capability discovery and negotiation."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._capabilities: Dict[str, Set[str]] = {}  # capability -> {agent_ids}
        self._bus = bus

    def advertise(self, agent_id: str, capabilities: Set[str]) -> None:
        """Replace the capabilities an agent claims."""
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id is required")
        if not isinstance(capabilities, set) or any(not isinstance(item, str) or not item for item in capabilities):
            raise ValueError("capabilities must be a set of names")
        for claimed in list(self._capabilities):
            self._capabilities[claimed].discard(agent_id)
            if not self._capabilities[claimed]:
                del self._capabilities[claimed]
        for capability in capabilities:
            self._capabilities.setdefault(capability, set()).add(agent_id)

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
        """Deploy a platoon from a template, or refuse if it would break the cap."""
        if template not in self.TEMPLATES:
            raise ValueError(f"unknown platoon template {template}")
        spec = self.TEMPLATES[template]
        if count is None:
            n = int(spec["count"])
        elif isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= N_CAP:
            raise ValueError("platoon count must be an integer from 1 to n-cap")
        else:
            n = count
        if len(mesh.agents()) + n > N_CAP:
            raise ValueError("n-cap")
        agents = []
        for _ in range(n):
            agent = mesh.join(set(spec["specialisations"]))
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
