"""MemoryTrinity composer — split from the memory monolith (v16.2)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus

from .types import MemoryQueryResult, UnifiedContext
from .store import MemoryStore
from .cag import CAGStore
from .mag import MAGStore

# =============================================================================
# MEMORY TRINITY — CROSS-TIER FUSION
# =============================================================================

class MemoryTrinity:
    """
    Orchestrates RAG, CAG, and MAG into a unified context window.

    Fusion strategy:
      1. Query all three tiers in parallel (conceptually; here sequential for simplicity).
      2. Deduplicate by semantic similarity.
      3. Re-rank by tier-specific weights: RAG=0.4, CAG=0.3, MAG=0.3.
      4. Build unified context with token budget enforcement.
      5. Emit provenance chain for audit.
    """

    def __init__(
        self,
        rag: MemoryStore,
        cag: CAGStore,
        mag: MAGStore,
        *,
        bus: Optional[EventBus] = None,
        max_context_tokens: int = 8000,
    ) -> None:
        self.rag = rag
        self.cag = cag
        self.mag = mag
        self.bus = bus
        self.max_context_tokens = max_context_tokens
        self._tier_weights = {"rag": 0.4, "cag": 0.3, "mag": 0.3}

    def query_unified(
        self,
        query_text: str,
        *,
        top_k_per_tier: int = 3,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> UnifiedContext:
        """Query all tiers and fuse into unified context."""
        self._validate_query(query_text,top_k_per_tier)
        if metadata_filter is not None and not isinstance(metadata_filter,dict):
            raise TypeError("metadata_filter must be a mapping")
        # Query each tier
        rag_results = self.rag.query(
            query_text, top_k=top_k_per_tier, metadata_filter=metadata_filter
        )
        cag_results = self.cag.query(
            query_text, top_k=top_k_per_tier, metadata_filter=metadata_filter
        )
        mag_results = self.mag.query(
            query_text, top_k=top_k_per_tier, metadata_filter=metadata_filter
        )

        return self._compose(
            query_text,
            rag_results,
            cag_results,
            mag_results,
            top_k_per_tier=top_k_per_tier,
        )

    def query_scoped(
        self,
        query_text: str,
        *,
        rag_scope: Dict[str,str],
        persona_id: str,
        user_id: str,
        top_k_per_tier: int = 3,
    ) -> UnifiedContext:
        """Fuse memory only after each tier independently enforces its authority scope."""
        self._validate_query(query_text,top_k_per_tier)
        if (
            not isinstance(rag_scope,dict)
            or not rag_scope
            or any(
                not isinstance(key,str)
                or not key
                or not isinstance(value,str)
                or not value
                for key,value in rag_scope.items()
            )
        ):
            raise ValueError("rag_scope must contain non-empty string keys and values")
        if not isinstance(persona_id,str) or not persona_id:
            raise ValueError("persona_id must be non-empty")
        if not isinstance(user_id,str) or not user_id:
            raise ValueError("user_id must be non-empty")

        rag_query=getattr(self.rag,"query_scoped",None)
        cag_query=getattr(self.cag,"query_scoped",None)
        mag_query=getattr(self.mag,"query_scoped",None)
        if not callable(rag_query) or not callable(cag_query) or not callable(mag_query):
            raise TypeError("all memory tiers must implement query_scoped")

        rag_results=rag_query(
            query_text,
            top_k=top_k_per_tier,
            scope=dict(rag_scope),
        )
        cag_results=cag_query(
            query_text,
            top_k=top_k_per_tier,
            scope={"persona_id":persona_id},
        )
        mag_results=mag_query(
            query_text,
            top_k=top_k_per_tier,
            scope={"user_id":user_id},
        )
        return self._compose(
            query_text,
            rag_results,
            cag_results,
            mag_results,
            top_k_per_tier=top_k_per_tier,
        )

    @staticmethod
    def _validate_query(query_text: str, top_k_per_tier: int) -> None:
        if not isinstance(query_text,str) or not query_text.strip():
            raise ValueError("query_text must be non-empty")
        if (
            isinstance(top_k_per_tier,bool)
            or not isinstance(top_k_per_tier,int)
            or top_k_per_tier<1
        ):
            raise ValueError("top_k_per_tier must be a positive integer")

    def _compose(
        self,
        query_text: str,
        rag_results: List[MemoryQueryResult],
        cag_results: List[MemoryQueryResult],
        mag_results: List[MemoryQueryResult],
        *,
        top_k_per_tier: int,
    ) -> UnifiedContext:
        # Apply tier weights
        for r in rag_results:
            r.fusion_contribution = r.score * self._tier_weights["rag"]
        for r in cag_results:
            r.fusion_contribution = r.score * self._tier_weights["cag"]
        for r in mag_results:
            r.fusion_contribution = r.score * self._tier_weights["mag"]

        # Deduplicate: if same text appears in multiple tiers, merge scores
        seen_texts: Dict[str, MemoryQueryResult] = {}
        for r in rag_results + cag_results + mag_results:
            text_hash = hashlib.sha256(r.chunk.text.encode()).hexdigest()[:16]
            if text_hash in seen_texts:
                seen_texts[text_hash].fusion_contribution += r.fusion_contribution
                seen_texts[text_hash].score = max(seen_texts[text_hash].score, r.score)
            else:
                seen_texts[text_hash] = r

        # Re-rank by fusion contribution
        all_results = sorted(
            seen_texts.values(),
            key=lambda item:(
                -item.fusion_contribution,
                item.chunk.source_tier,
                item.chunk.id,
            ),
        )

        # Build context within token budget
        tokens_used = 0
        context_parts: List[str] = []
        provenance: List[str] = []

        for r in all_results:
            text = f"[{r.chunk.source_tier.upper()}] {r.chunk.text}"
            tokens = len(text) // 4
            if tokens_used + tokens > self.max_context_tokens:
                break
            context_parts.append(text)
            tokens_used += tokens
            provenance.append(f"{r.chunk.source_tier}:{r.chunk.id}(score={r.score:.3f})")

        # Emit event
        if self.bus:
            self.bus.publish(
                DomainEvent(
                    topic="memory.trinity.query",
                    payload={
                        "query": query_text,
                        "tiers_queried": ["rag", "cag", "mag"],
                        "results_count": len(all_results),
                        "tokens_used": tokens_used,
                        "provenance": provenance,
                    },
                    correlation_id=f"mem_{hashlib.sha256(query_text.encode()).hexdigest()[:12]}",
                )
            )

        return UnifiedContext(
            facts=rag_results,
            persona_frame=cag_results,
            personal_history=mag_results,
            combined_score=sum(r.fusion_contribution for r in all_results),
            token_estimate=tokens_used,
            provenance_chain=provenance,
        )

    def health(self) -> Dict[str, Any]:
        return {
            "trinity": {
                "rag": self.rag.health(),
                "cag": self.cag.health(),
                "mag": self.mag.health(),
            },
            "max_context_tokens": self.max_context_tokens,
            "tier_weights": self._tier_weights,
            "status": "healthy",
        }
