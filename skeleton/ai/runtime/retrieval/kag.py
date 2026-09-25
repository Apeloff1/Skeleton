"""
Skeleton Retrieval — KAG plane: knowledge-augmented generation

Provides:
- KnowledgeGraph: Typed entity-relation store with traversal
- KAGRetriever: Graph-based retrieval compatible with QuadRetriever

The KAG plane answers queries by matching entities in the graph and
returning relation paths, complementing the semantic (RAG),
contextual (CAG), and episodic (MAG) planes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple



@dataclass(frozen=True)
class FactAnnotation:
    """Confidence and provenance kept beside a triple, not inside its identity."""

    confidence: float
    provenance: str


def validate_fact_confidence(confidence: float) -> float:
    """Reject bools and values outside the unit interval."""
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be numeric")
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return value


@dataclass(frozen=True)
class Triple:
    """A subject-predicate-object fact."""
    subject: str
    predicate: str
    obj: str

    def to_dict(self) -> Dict[str, str]:
        return {"subject": self.subject, "predicate": self.predicate, "object": self.obj}


class KnowledgeGraph:
    """Typed entity-relation graph with traversal queries."""

    def __init__(self):
        self._triples: Set[Triple] = set()
        self._by_subject: Dict[str, Set[Triple]] = {}
        self._by_object: Dict[str, Set[Triple]] = {}
        self._by_predicate: Dict[str, Set[Triple]] = {}
        self._annotations: Dict[Triple, FactAnnotation] = {}

    def add(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        confidence: float = 1.0,
        provenance: str = "",
    ) -> Triple:
        confidence = validate_fact_confidence(confidence)
        if not isinstance(provenance, str):
            raise TypeError("provenance must be a string")
        t = Triple(subject.lower().strip(), predicate.lower().strip(), obj.lower().strip())
        if t not in self._triples:
            self._triples.add(t)
            self._by_subject.setdefault(t.subject, set()).add(t)
            self._by_object.setdefault(t.obj, set()).add(t)
            self._by_predicate.setdefault(t.predicate, set()).add(t)
        previous = self._annotations.get(t)
        if previous is None:
            self._annotations[t] = FactAnnotation(confidence, provenance)
        else:
            kept_confidence = max(previous.confidence, confidence)
            if provenance and (not previous.provenance or confidence >= previous.confidence):
                kept_provenance = provenance
            else:
                kept_provenance = previous.provenance
            self._annotations[t] = FactAnnotation(kept_confidence, kept_provenance)
        return t

    def annotation_for(self, subject: str, predicate: str, obj: str) -> FactAnnotation:
        t = Triple(subject.lower().strip(), predicate.lower().strip(), obj.lower().strip())
        return self._annotations.get(t, FactAnnotation(1.0, ""))

    def add_many(self, facts: List[Tuple[str, str, str]]) -> int:
        return sum(1 for s, p, o in facts if self.add(s, p, o))

    def neighbors(self, entity: str, direction: str = "both") -> List[Triple]:
        entity = entity.lower().strip()
        out = list(self._by_subject.get(entity, set())) if direction in ("out", "both") else []
        inc = list(self._by_object.get(entity, set())) if direction in ("in", "both") else []
        return out + inc

    def find_entities(self, text: str) -> List[str]:
        """Extract entities mentioned in text (longest-match over known nodes)."""
        text_l = text.lower()
        entities = set(self._by_subject.keys()) | set(self._by_object.keys())
        return sorted((e for e in entities if e in text_l), key=len, reverse=True)

    def paths(self, start: str, end: str, max_depth: int = 3) -> List[List[Triple]]:
        """BFS for relation paths between two entities."""
        start, end = start.lower().strip(), end.lower().strip()
        found: List[List[Triple]] = []
        queue: List[Tuple[str, List[Triple]]] = [(start, [])]
        visited = {start}

        while queue:
            node, path = queue.pop(0)
            if len(path) >= max_depth:
                continue
            for t in self._by_subject.get(node, set()):
                nxt = t.obj
                new_path = path + [t]
                if nxt == end:
                    found.append(new_path)
                elif nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, new_path))
        return found

    def stats(self) -> Dict[str, Any]:
        return {
            "triples": len(self._triples),
            "entities": len(set(self._by_subject) | set(self._by_object)),
            "predicates": len(self._by_predicate),
        }


class KAGRetriever:
    """Graph-based retrieval plane, QuadRetriever-compatible.

    `query(text)` finds entities in the text, expands to neighbor
    triples, and returns them as ScoredResults for fusion.
    """

    def __init__(self, graph: Optional[KnowledgeGraph] = None):
        self.graph = graph or KnowledgeGraph()
        self._stats = {"queries": 0, "hits": 0}

    def query(self, text: str, top_k: int = 5) -> List[Any]:
        from skeleton.retrieval.fusion import ScoredResult

        self._stats["queries"] += 1
        entities = self.graph.find_entities(text)
        results: List[ScoredResult] = []

        for rank, entity in enumerate(entities[:3]):
            for t in self.graph.neighbors(entity)[:top_k]:
                content = f"{t.subject} {t.predicate.replace('_', ' ')} {t.obj}"
                note = self.graph.annotation_for(t.subject, t.predicate, t.obj)
                score = (1.0 / (1 + rank)) * note.confidence
                results.append(ScoredResult(
                    fragment_id=f"kag-{t.subject}-{t.predicate}-{t.obj}",
                    content=content,
                    score=score,
                    plane="kag",
                    provenance=note.provenance or f"graph:{entity}",
                    metadata={"confidence": note.confidence},
                ))

        self._stats["hits"] += len(results)
        return results[:top_k]

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, **self.graph.stats()}
