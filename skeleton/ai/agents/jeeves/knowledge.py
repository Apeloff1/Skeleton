"""Knowledge graph — the concept lattice Jeeves tutors over.

The self-learning matrices track *how well* a learner knows things; this
graph tracks *what there is to know* and how concepts depend on each
other. It is the substrate ZPD tracking actually needs: the zone of
proximal development is defined relative to a prerequisite structure, and
without the graph the ZPD is a vibe.

Design
------
- Nodes are concepts with a domain and difficulty; edges are typed:
  PREREQUISITE_OF, RELATES_TO, PART_OF, CONTRASTS_WITH.
- ``ready_to_learn(known)`` returns concepts whose prerequisites are all
  known — the executable definition of the ZPD frontier.
- ``learning_path(target, known)`` returns a topological order from the
  learner's current knowledge to the target concept, so tutoring plans
  are derived, not improvised.
- Mastery levels (0–4, matching the four learning stages) live on the
  *learner's* copy of a concept, not the concept itself — the graph is
  shared, the progress is per-user.

Deterministic, pure domain, JSON-serialisable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from skeleton.kernel.errors import JeevesError
from skeleton.kernel.events import DomainEvent, EventBus

MAX_CONCEPTS = 10_000
MAX_EDGES = 50_000
MAX_CONCEPT_ID_CHARS = 256
MAX_CONCEPT_NAME_CHARS = 1_024
MAX_DOMAIN_CHARS = 256


class ConceptError(JeevesError):
    code = "JEE.CONCEPT"
    http_status = 422


def _bounded_text(name: str, value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConceptError(f"{name} must be a non-empty string")
    if len(value) > maximum:
        raise ConceptError(f"{name} is too long", context={"max_chars": maximum})
    return value


class EdgeType(Enum):
    PREREQUISITE_OF = auto()
    RELATES_TO = auto()
    PART_OF = auto()
    CONTRASTS_WITH = auto()


@dataclass(frozen=True)
class Concept:
    concept_id: str
    name: str
    domain: str
    difficulty: float = 0.5        # 0–1, used to order within the ZPD

    def __post_init__(self) -> None:
        _bounded_text("concept_id", self.concept_id, MAX_CONCEPT_ID_CHARS)
        _bounded_text("name", self.name, MAX_CONCEPT_NAME_CHARS)
        _bounded_text("domain", self.domain, MAX_DOMAIN_CHARS)
        if isinstance(self.difficulty, bool) or not isinstance(self.difficulty, (int, float)):
            raise ConceptError("difficulty must be numeric")
        difficulty = float(self.difficulty)
        if not math.isfinite(difficulty) or not 0.0 <= difficulty <= 1.0:
            raise ConceptError("difficulty must be finite and between 0 and 1")
        object.__setattr__(self, "difficulty", difficulty)


@dataclass(frozen=True)
class ConceptEdge:
    source: str
    target: str
    kind: EdgeType


class KnowledgeGraph:
    """The shared concept lattice with bounded, acyclic prerequisites."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 max_concepts: int = MAX_CONCEPTS,
                 max_edges: int = MAX_EDGES) -> None:
        if isinstance(max_concepts, bool) or not isinstance(max_concepts, int) or max_concepts < 1:
            raise ConceptError("max_concepts must be a positive integer")
        if isinstance(max_edges, bool) or not isinstance(max_edges, int) or max_edges < 1:
            raise ConceptError("max_edges must be a positive integer")
        self._concepts: Dict[str, Concept] = {}
        self._edges: List[ConceptEdge] = []
        self._bus = bus
        self._max_concepts = max_concepts
        self._max_edges = max_edges

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def add_concept(self, concept: Concept) -> None:
        if not isinstance(concept, Concept):
            raise ConceptError("concept must be a Concept")
        if concept.concept_id in self._concepts:
            raise ConceptError("concept exists",
                               context={"concept": concept.concept_id})
        if len(self._concepts) >= self._max_concepts:
            raise ConceptError("concept capacity reached",
                               context={"max_concepts": self._max_concepts})
        self._concepts[concept.concept_id] = concept

    def add_edge(self, source: str, target: str, kind: EdgeType) -> None:
        source = _bounded_text("source", source, MAX_CONCEPT_ID_CHARS)
        target = _bounded_text("target", target, MAX_CONCEPT_ID_CHARS)
        if not isinstance(kind, EdgeType):
            raise ConceptError("kind must be an EdgeType")
        for cid in (source, target):
            if cid not in self._concepts:
                raise ConceptError("edge references unknown concept",
                                   context={"concept": cid})

        edge = ConceptEdge(source, target, kind)
        if edge in self._edges:
            return
        if len(self._edges) >= self._max_edges:
            raise ConceptError("edge capacity reached",
                               context={"max_edges": self._max_edges})

        if kind is EdgeType.PREREQUISITE_OF:
            if source == target or target in self._prerequisite_closure(source):
                raise ConceptError(
                    "prerequisite edge would create a cycle",
                    context={"source": source, "target": target},
                )
        self._edges.append(edge)

    def prerequisites(self, concept_id: str) -> Set[str]:
        """Direct prerequisites of a concept (edges pointing at it)."""
        concept_id = _bounded_text("concept_id", concept_id, MAX_CONCEPT_ID_CHARS)
        return {e.source for e in self._edges
                if e.target == concept_id and e.kind == EdgeType.PREREQUISITE_OF}

    def _prerequisite_closure(self, concept_id: str) -> Set[str]:
        """All transitive prerequisites."""
        seen: Set[str] = set()
        stack = [concept_id]
        while stack:
            current = stack.pop()
            for pre in self.prerequisites(current):
                if pre not in seen:
                    seen.add(pre)
                    stack.append(pre)
        return seen

    # ------------------------------------------------------------------
    # Learning queries
    # ------------------------------------------------------------------

    def ready_to_learn(self, known: Set[str], *,
                       domain: Optional[str] = None) -> List[Concept]:
        """Concepts whose full prerequisite closure is known — the ZPD frontier."""
        if not isinstance(known, set) or any(not isinstance(cid, str) for cid in known):
            raise ConceptError("known must be a set of concept ids")
        if domain is not None:
            domain = _bounded_text("domain", domain, MAX_DOMAIN_CHARS)
        ready: List[Concept] = []
        for concept in self._concepts.values():
            if concept.concept_id in known:
                continue
            if domain and concept.domain != domain:
                continue
            if self._prerequisite_closure(concept.concept_id) <= known:
                ready.append(concept)
        return sorted(ready, key=lambda c: (c.difficulty, c.concept_id))

    def learning_path(self, target: str, known: Set[str]) -> List[str]:
        """Ordered concept ids from the learner's frontier to the target."""
        target = _bounded_text("target", target, MAX_CONCEPT_ID_CHARS)
        if not isinstance(known, set) or any(not isinstance(cid, str) for cid in known):
            raise ConceptError("known must be a set of concept ids")
        if target not in self._concepts:
            raise ConceptError("unknown target concept",
                               context={"concept": target})
        needed = self._prerequisite_closure(target) - known
        path: List[str] = []
        mastered = set(known)
        while needed:
            ready = [cid for cid in needed
                     if self._prerequisite_closure(cid) <= mastered]
            if not ready:
                raise ConceptError("prerequisite cycle blocks path",
                                   context={"target": target})
            ready.sort(key=lambda cid: (self._concepts[cid].difficulty, cid))
            nxt = ready[0]
            path.append(nxt)
            mastered.add(nxt)
            needed.discard(nxt)
        path.append(target)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="jeeves.knowledge.path_computed",
                    payload={"target": target, "hops": len(path),
                             "known_at_start": len(known)},
                    correlation_id=f"kg_{target}",
                )
            )
        return path

    def stats(self) -> Dict[str, Any]:
        domains: Dict[str, int] = {}
        for c in self._concepts.values():
            domains[c.domain] = domains.get(c.domain, 0) + 1
        return {
            "concepts": len(self._concepts),
            "edges": len(self._edges),
            "domains": domains,
            "capacity": {
                "concepts": self._max_concepts,
                "edges": self._max_edges,
            },
        }
