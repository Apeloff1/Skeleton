"""
Skeleton Jeeves — KAG citations

Grounds Jeeves responses in the knowledge graph: every reply can
carry citations — the graph triples relevant to the query — so users
(and downstream tools) can trace which facts an answer stands on.

Provides:
- Citation: a cited triple with relevance score
- CitationEngine: extract query entities → find supporting triples →
  format citations inline or as an appendix
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Citation:
    """A single cited fact from the knowledge graph."""
    subject: str
    predicate: str
    obj: str
    score: float
    entity_matched: str

    def render(self) -> str:
        return f"{self.subject} {self.predicate.replace('_', ' ')} {self.obj}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact": self.render(),
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.obj,
            "score": round(self.score, 3),
            "matched_entity": self.entity_matched,
        }


class CitationEngine:
    """Find knowledge-graph support for a query and format citations."""

    def __init__(self, kag: Optional[Any] = None, max_citations: int = 5):
        self._kag = kag  # KAGRetriever (graph access)
        self.max_citations = max_citations
        self._stats = {"queries": 0, "cited": 0}

    def cite(self, query: str, context_terms: Optional[List[str]] = None) -> List[Citation]:
        """Find triples supporting a query.

        Entity extraction: graph entities found in the query text,
        plus optional context terms (e.g. SAM expansions from Jeeves).
        Score: 1/(1+entity_rank) — earlier-mentioned entities rank higher.
        """
        self._stats["queries"] += 1
        if self._kag is None:
            return []

        graph = self._kag.graph
        text = query
        if context_terms:
            text = query + " " + " ".join(context_terms)

        entities = graph.find_entities(text)
        citations: List[Citation] = []
        seen = set()

        for rank, entity in enumerate(entities[:3]):
            for triple in graph.neighbors(entity):
                key = (triple.subject, triple.predicate, triple.obj)
                if key in seen:
                    continue
                seen.add(key)
                citations.append(Citation(
                    subject=triple.subject,
                    predicate=triple.predicate,
                    obj=triple.obj,
                    score=1.0 / (1 + rank),
                    entity_matched=entity,
                ))

        citations.sort(key=lambda c: c.score, reverse=True)
        out = citations[: self.max_citations]
        self._stats["cited"] += len(out)
        return out

    def format_appendix(self, citations: List[Citation]) -> str:
        """Render citations as a trailing appendix block."""
        if not citations:
            return ""
        lines = ["", "Sources (knowledge graph):"]
        for i, c in enumerate(citations, 1):
            lines.append(f"  [{i}] {c.render()}")
        return "\n".join(lines)

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
