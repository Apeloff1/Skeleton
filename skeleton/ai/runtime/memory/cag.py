"""CAG — persona context store — split from the memory monolith (v16.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import RagQueryError

from .types import MemoryChunk, MemoryQueryResult
from .store import MemoryStore

# =============================================================================
# CAG — CONTEXT-AUGMENTED GENERATION
# =============================================================================

@dataclass
class PersonaContext:
    """A hot-swappable persona context with importance scoring."""
    persona_id: str
    name: str
    system_prompt: str
    knowledge_graph: Dict[str, List[str]] = field(default_factory=dict)
    importance_scores: Dict[str, float] = field(default_factory=dict)
    max_tokens: int = 4000
    current_tokens: int = 0

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        return len(text) // 4

    def add_knowledge(self, key: str, facts: List[str], importance: float = 1.0) -> None:
        """Add facts to the knowledge graph with importance weighting."""
        self.knowledge_graph[key] = facts
        self.importance_scores[key] = importance
        self.current_tokens += sum(self.estimate_tokens(f) for f in facts)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        """Evict lowest-importance knowledge if over token budget."""
        while self.current_tokens > self.max_tokens and self.knowledge_graph:
            # Find lowest importance
            lowest_key = min(self.importance_scores, key=self.importance_scores.get)
            facts = self.knowledge_graph.pop(lowest_key)
            self.current_tokens -= sum(self.estimate_tokens(f) for f in facts)
            del self.importance_scores[lowest_key]

    def get_context_window(self, query: str) -> str:
        """Build context window prioritised by relevance to query + importance."""
        # Score each knowledge node by keyword overlap + importance
        query_words = set(query.lower().split())
        scored: List[Tuple[float, str, List[str]]] = []
        for key, facts in self.knowledge_graph.items():
            overlap = len(set(key.lower().split()) & query_words)
            importance = self.importance_scores.get(key, 1.0)
            score = overlap * 0.3 + importance * 0.7
            scored.append((score, key, facts))

        scored.sort(reverse=True)

        tokens_used = self.estimate_tokens(self.system_prompt)
        parts: List[str] = [self.system_prompt]

        for score, key, facts in scored:
            fact_text = f"[{key}]: " + "; ".join(facts)
            fact_tokens = self.estimate_tokens(fact_text)
            if tokens_used + fact_tokens > self.max_tokens:
                break
            parts.append(fact_text)
            tokens_used += fact_tokens

        return "\n\n".join(parts)


class CAGStore(MemoryStore):
    """
    Context-Augmented Generation store.
    Manages persona contexts with hot-swapping and knowledge-graph pre-loading.
    """

    def __init__(self) -> None:
        self._personas: Dict[str, PersonaContext] = {}
        self._active_persona_id: Optional[str] = None

    def create_persona(
        self,
        persona_id: str,
        name: str,
        system_prompt: str,
        max_tokens: int = 4000,
    ) -> PersonaContext:
        persona = PersonaContext(
            persona_id=persona_id,
            name=name,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        self._personas[persona_id] = persona
        if self._active_persona_id is None:
            self._active_persona_id = persona_id
        return persona

    def switch_persona(self, persona_id: str) -> None:
        if persona_id not in self._personas:
            raise RagQueryError(f"Persona {persona_id} not found")
        self._active_persona_id = persona_id

    def add(self, chunk: MemoryChunk) -> None:
        """Add knowledge to the active persona's knowledge graph."""
        if not self._active_persona_id:
            raise RagQueryError("No active persona")
        persona = self._personas[self._active_persona_id]
        # Extract key from metadata or use chunk id
        key = chunk.metadata.get("topic", chunk.id)
        facts = chunk.text.split("\n") if "\n" in chunk.text else [chunk.text]
        importance = chunk.metadata.get("importance", 1.0)
        persona.add_knowledge(key, facts, importance)

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        if not self._active_persona_id:
            return []
        persona = self._personas[self._active_persona_id]
        context = persona.get_context_window(query_text)

        # Return the context as a single synthetic chunk
        chunk = MemoryChunk(
            id=f"cag_{self._active_persona_id}",
            text=context,
            metadata={"persona": persona.name, "tier": "cag"},
            source_tier="cag",
            confidence=1.0,
        )
        return [MemoryQueryResult(chunk=chunk, score=1.0, rank=1)]

    def delete(self, chunk_id: str) -> bool:
        # In CAG, deletion means removing a knowledge node from active persona
        if not self._active_persona_id:
            return False
        persona = self._personas[self._active_persona_id]
        for key in list(persona.knowledge_graph.keys()):
            if key == chunk_id or f"cag_{key}" == chunk_id:
                del persona.knowledge_graph[key]
                del persona.importance_scores[key]
                return True
        return False

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "cag",
            "personas": len(self._personas),
            "active_persona": self._active_persona_id,
            "status": "healthy" if self._active_persona_id else "idle",
        }
