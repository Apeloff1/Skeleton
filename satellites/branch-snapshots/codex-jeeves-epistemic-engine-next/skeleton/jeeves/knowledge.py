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

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

from skeleton.kernel.errors import JeevesError
from skeleton.kernel.events import DomainEvent, EventBus


class ConceptError(JeevesError):
    code = "JEE.CONCEPT"
    http_status = 422


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


@dataclass(frozen=True)
class ConceptEdge:
    source: str
    target: str
    kind: EdgeType


class KnowledgeGraph:
    """The shared concept lattice."""

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._concepts: Dict[str, Concept] = {}
        self._edges: List[ConceptEdge] = []
        self._bus = bus

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------

    def add_concept(self, concept: Concept) -> None:
        if concept.concept_id in self._concepts:
            raise ConceptError("concept exists",
                               context={"concept": concept.concept_id})
        self._concepts[concept.concept_id] = concept

    def add_edge(self, source: str, target: str, kind: EdgeType) -> None:
        for cid in (source, target):
            if cid not in self._concepts:
                raise ConceptError("edge references unknown concept",
                                   context={"concept": cid})
        self._edges.append(ConceptEdge(source, target, kind))

    def prerequisites(self, concept_id: str) -> Set[str]:
        """Direct prerequisites of a concept (edges pointing at it)."""
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
        ready: List[Concept] = []
        for concept in self._concepts.values():
            if concept.concept_id in known:
                continue
            if domain and concept.domain != domain:
                continue
            if self._prerequisite_closure(concept.concept_id) <= known:
                ready.append(concept)
        return sorted(ready, key=lambda c: c.difficulty)

    def learning_path(self, target: str, known: Set[str]) -> List[str]:
        """Ordered concept ids from the learner's frontier to the target."""
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
            ready.sort(key=lambda cid: self._concepts[cid].difficulty)
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
        }
