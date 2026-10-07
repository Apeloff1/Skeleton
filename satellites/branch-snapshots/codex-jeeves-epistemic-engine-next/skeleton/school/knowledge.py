"""Learner-facing knowledge graph and epistemic state for Jeeves.

The source systems contain encyclopedic records, facts, discovery gates and
progression metadata.  Skeleton turns those ideas into a general knowledge
substrate: concepts are connected by typed relations, every assertion can
carry provenance and confidence, and learner knowledge is tracked separately
from canonical knowledge.

The graph is deliberately deterministic and provider-neutral.  A future
retrieval/embedding adapter can feed it richer candidates without changing the
reasoning contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence


class RelationKind(str, Enum):
    PREREQUISITE = "prerequisite"
    PART_OF = "part_of"
    INSTANCE_OF = "instance_of"
    RELATED = "related"
    CONTRASTS = "contrasts"
    CAUSES = "causes"
    SUPPORTS = "supports"
    APPLIES_TO = "applies_to"
    EXAMPLE_OF = "example_of"
    TRANSFERS_TO = "transfers_to"


@dataclass(frozen=True)
class KnowledgeNode:
    node_id: str
    title: str
    description: str = ""
    tags: tuple[str, ...] = ()
    difficulty: float = 0.5
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeEdge:
    source: str
    target: str
    relation: RelationKind
    weight: float = 1.0
    source_id: str = ""


@dataclass(frozen=True)
class KnowledgeAssertion:
    assertion_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_id: str = ""
    evidence: tuple[str, ...] = ()


@dataclass
class KnowledgeGraph:
    nodes: dict[str, KnowledgeNode] = field(default_factory=dict)
    edges: list[KnowledgeEdge] = field(default_factory=list)
    assertions: dict[str, KnowledgeAssertion] = field(default_factory=dict)

    def add_node(self, node: KnowledgeNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: KnowledgeEdge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("knowledge edge endpoints must exist")
        if not 0.0 <= edge.weight <= 1.0:
            raise ValueError("edge weight must be in [0, 1]")
        self.edges.append(edge)

    def add_assertion(self, assertion: KnowledgeAssertion) -> None:
        if assertion.subject not in self.nodes:
            raise ValueError("assertion subject must exist")
        if not 0.0 <= assertion.confidence <= 1.0:
            raise ValueError("assertion confidence must be in [0, 1]")
        self.assertions[assertion.assertion_id] = assertion

    def neighbors(self, node_id: str, relation: RelationKind | None = None) -> tuple[KnowledgeEdge, ...]:
        return tuple(
            edge for edge in self.edges
            if edge.source == node_id and (relation is None or edge.relation == relation)
        )

    def prerequisites(self, node_id: str) -> tuple[str, ...]:
        return tuple(edge.target for edge in self.neighbors(node_id, RelationKind.PREREQUISITE))

    def ancestors(self, node_id: str, *, max_depth: int = 32) -> tuple[str, ...]:
        seen: set[str] = set()
        frontier = [(node_id, 0)]
        while frontier:
            current, depth = frontier.pop()
            if depth >= max_depth:
                continue
            for edge in self.neighbors(current, RelationKind.PREREQUISITE):
                if edge.target not in seen:
                    seen.add(edge.target)
                    frontier.append((edge.target, depth + 1))
        return tuple(sorted(seen))

    def validate(self) -> None:
        for edge in self.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise ValueError(f"dangling knowledge edge: {edge.source}->{edge.target}")
        for node_id in self.nodes:
            self._validate_acyclic(node_id)

    def _validate_acyclic(self, start: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("knowledge prerequisite cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for target in self.prerequisites(node_id):
                visit(target)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(start)


@dataclass
class KnowledgeState:
    """Learner belief over graph nodes, independent from canonical truth."""

    confidence: dict[str, float] = field(default_factory=dict)
    exposure: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    misconceptions: dict[str, str] = field(default_factory=dict)

    def observe(self, node_id: str, score: float, *, evidence: str = "") -> None:
        score = max(0.0, min(1.0, score))
        prior = self.confidence.get(node_id, 0.0)
        count = self.exposure.get(node_id, 0)
        alpha = 0.6 if count == 0 else 1.0 / min(8, count + 2)
        self.confidence[node_id] = prior * (1.0 - alpha) + score * alpha
        self.exposure[node_id] = count + 1
        if evidence:
            self.evidence.setdefault(node_id, []).append(evidence)

    def mark_misconception(self, node_id: str, description: str) -> None:
        self.misconceptions[node_id] = description

    def mastery(self, node_id: str) -> float:
        return max(0.0, min(1.0, self.confidence.get(node_id, 0.0)))

    def ready_for(self, graph: KnowledgeGraph, node_id: str, threshold: float = 0.7) -> bool:
        return all(self.mastery(prerequisite) >= threshold for prerequisite in graph.prerequisites(node_id))


@dataclass(frozen=True)
class KnowledgeCandidate:
    node_id: str
    score: float
    reason: str
    path: tuple[str, ...] = ()


def rank_knowledge(
    graph: KnowledgeGraph,
    state: KnowledgeState,
    *,
    query_terms: Sequence[str] = (),
    goals: Sequence[str] = (),
    limit: int = 8,
) -> tuple[KnowledgeCandidate, ...]:
    """Rank knowledge by semantic-ish lexical match, readiness and learning gap."""
    terms = {term.casefold() for term in query_terms if term.strip()}
    goal_set = {goal.casefold() for goal in goals}
    candidates: list[KnowledgeCandidate] = []
    for node in graph.nodes.values():
        text = " ".join((node.node_id, node.title, node.description, *node.tags)).casefold()
        lexical = sum(1 for term in terms if term in text) / max(1, len(terms))
        goal = 0.25 if any(g in text for g in goal_set) else 0.0
        gap = 1.0 - state.mastery(node.node_id)
        ready = 0.2 if state.ready_for(graph, node.node_id) else -0.25
        misconception = -0.35 if node.node_id in state.misconceptions else 0.0
        score = 0.45 * gap + 0.25 * lexical + goal + ready + misconception
        reason = "learning gap"
        if lexical:
            reason = "query-aligned knowledge"
        if node.node_id in state.misconceptions:
            reason = "misconception repair"
        candidates.append(KnowledgeCandidate(node.node_id, score, reason, graph.ancestors(node.node_id)))
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.node_id))[:limit])


def infer_ready_frontier(graph: KnowledgeGraph, state: KnowledgeState, *, threshold: float = 0.7) -> tuple[str, ...]:
    """Return graph nodes whose prerequisites are mastered but whose own mastery is not."""
    return tuple(
        node.node_id
        for node in sorted(graph.nodes.values(), key=lambda item: item.node_id)
        if state.mastery(node.node_id) < threshold and state.ready_for(graph, node.node_id, threshold)
    )
