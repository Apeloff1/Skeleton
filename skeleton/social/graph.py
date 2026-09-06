"""
Skeleton Social — Multi-agent interaction and reputation

Provides:
- SocialGraph: Agent relationship tracking
- ReputationEngine: Trust scoring between agents
- InteractionLog: Record of agent interactions
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class Interaction:
    """A single interaction between two agents."""
    from_agent: str
    to_agent: str
    interaction_type: str
    outcome: float  # -1.0 to 1.0
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)


class SocialGraph:
    """Track relationships and interactions between agents."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._interactions: List[Interaction] = []
        self._relationships: Dict[str, Dict[str, float]] = {}  # agent -> {other_agent: strength}
        self._bus = bus
        self._stats = {"interactions": 0}

    def record_interaction(self, from_agent: str, to_agent: str, interaction_type: str, outcome: float, context: Optional[Dict[str, Any]] = None) -> None:
        """Record an interaction between two agents."""
        interaction = Interaction(
            from_agent=from_agent,
            to_agent=to_agent,
            interaction_type=interaction_type,
            outcome=outcome,
            context=context or {},
        )
        self._interactions.append(interaction)
        self._stats["interactions"] += 1
        
        # Update relationship strength
        key = f"{from_agent}:{to_agent}"
        current = self._relationships.get(from_agent, {}).get(to_agent, 0.0)
        # Moving average with decay
        new_strength = current * 0.9 + outcome * 0.1
        self._relationships.setdefault(from_agent, {})[to_agent] = max(-1.0, min(1.0, new_strength))
        
        if self._bus:
            self._bus.emit("social.interaction", {
                "from": from_agent,
                "to": to_agent,
                "type": interaction_type,
                "outcome": outcome,
            })

    def get_relationship(self, agent_a: str, agent_b: str) -> float:
        """Get relationship strength between two agents (-1.0 to 1.0)."""
        return self._relationships.get(agent_a, {}).get(agent_b, 0.0)

    def get_neighbors(self, agent: str, min_strength: float = 0.0) -> List[str]:
        """Get agents with positive relationship strength."""
        relationships = self._relationships.get(agent, {})
        return [other for other, strength in relationships.items() if strength >= min_strength]

    def get_network(self, agent: str, depth: int = 1) -> Dict[str, Any]:
        """Get the social network around an agent up to a depth."""
        if depth <= 0:
            return {agent: []}
        
        direct = self.get_neighbors(agent)
        network = {agent: direct}
        
        for neighbor in direct:
            if neighbor not in network:
                network[neighbor] = self.get_neighbors(neighbor)
        
        return network

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "agents": len(self._relationships),
            "relationships": sum(len(r) for r in self._relationships.values()),
        }


class ReputationEngine:
    """Compute trust and reputation scores for agents."""

    def __init__(self, graph: SocialGraph, bus: Optional[EventBus] = None):
        self._graph = graph
        self._bus = bus
        self._reputation: Dict[str, float] = {}
        self._global_reputation: Dict[str, float] = {}

    def compute_reputation(self, agent: str, method: str = "pagerank") -> float:
        """Compute reputation score for an agent.
        
        Methods:
        - simple: Average of relationship strengths
        - weighted: Weighted by interaction count
        - pagerank: PageRank-style centrality
        """
        if method == "simple":
            relationships = self._graph._relationships.get(agent, {})
            if not relationships:
                return 0.0
            return sum(relationships.values()) / len(relationships)
        
        elif method == "weighted":
            interactions = [i for i in self._graph._interactions if i.to_agent == agent or i.from_agent == agent]
            if not interactions:
                return 0.0
            total_weight = sum(abs(i.outcome) for i in interactions)
            if total_weight == 0:
                return 0.0
            weighted_sum = sum(i.outcome * abs(i.outcome) for i in interactions)
            return weighted_sum / total_weight
        
        elif method == "pagerank":
            # Simplified PageRank
            return self._simple_pagerank(agent)
        
        return 0.0

    def _simple_pagerank(self, agent: str, iterations: int = 10, damping: float = 0.85) -> float:
        """Compute simplified PageRank for an agent."""
        agents = set(self._graph._relationships.keys())
        for other in self._graph._relationships:
            agents.update(self._graph._relationships[other].keys())
        
        if not agents:
            return 0.0
        
        scores = {a: 1.0 / len(agents) for a in agents}
        
        for _ in range(iterations):
            new_scores = {}
            for a in agents:
                score = (1 - damping) / len(agents)
                for other in agents:
                    relationships = self._graph._relationships.get(other, {})
                    if a in relationships and relationships[a] > 0:
                        out_count = sum(1 for v in relationships.values() if v > 0)
                        if out_count > 0:
                            score += damping * scores[other] * relationships[a] / out_count
                new_scores[a] = score
            scores = new_scores
        
        return scores.get(agent, 0.0)

    def get_ranking(self, top_n: int = 10) -> List[tuple[str, float]]:
        """Get top-N agents by reputation."""
        agents = set(self._graph._relationships.keys())
        for other in self._graph._relationships:
            agents.update(self._graph._relationships[other].keys())
        
        scores = [(agent, self.compute_reputation(agent)) for agent in agents]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]

    def stats(self) -> Dict[str, Any]:
        return {
            "agents_ranked": len(self._reputation),
            "method": "pagerank",
        }


class InteractionLog:
    """Immutable log of all agent interactions."""

    def __init__(self, max_size: int = 100000):
        self._interactions: List[Interaction] = []
        self._max_size = max_size
        self._by_type: Dict[str, List[Interaction]] = {}
        self._by_agent: Dict[str, List[Interaction]] = {}

    def append(self, interaction: Interaction) -> None:
        """Add an interaction to the log."""
        self._interactions.append(interaction)
        
        # Index by type
        self._by_type.setdefault(interaction.interaction_type, []).append(interaction)
        
        # Index by agent
        self._by_agent.setdefault(interaction.from_agent, []).append(interaction)
        self._by_agent.setdefault(interaction.to_agent, []).append(interaction)
        
        # Trim if too large
        if len(self._interactions) > self._max_size:
            removed = self._interactions[:self._max_size // 10]
            self._interactions = self._interactions[self._max_size // 10:]
            # Rebuild indices (simplified)
            self._by_type.clear()
            self._by_agent.clear()
            for i in self._interactions:
                self._by_type.setdefault(i.interaction_type, []).append(i)
                self._by_agent.setdefault(i.from_agent, []).append(i)
                self._by_agent.setdefault(i.to_agent, []).append(i)

    def query(self, agent: Optional[str] = None, interaction_type: Optional[str] = None, since: Optional[float] = None) -> List[Interaction]:
        """Query interactions by agent, type, or time."""
        results = self._interactions
        
        if agent:
            results = [i for i in results if i.from_agent == agent or i.to_agent == agent]
        
        if interaction_type:
            results = [i for i in results if i.interaction_type == interaction_type]
        
        if since:
            results = [i for i in results if i.timestamp >= since]
        
        return results

    def stats(self) -> Dict[str, Any]:
        return {
            "total": len(self._interactions),
            "types": len(self._by_type),
            "agents": len(self._by_agent),
        }
