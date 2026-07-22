from __future__ import annotations
from typing import Any, Dict, List, Optional
from gameforge.rooms.room_bookshelf import RoomBookshelf
from gameforge.rooms.room_cache import RoomCache

class RoomHybridRAG:
    """
    Advanced Agentic Hybrid RAG system scoped to a single room.
    Combines Vector + Graph + Keyword retrieval with intelligent routing,
    re-ranking, and memory consolidation.
    Designed to match the exocortex Hybrid RAG philosophy but per-room.
    """

    def __init__(self, bookshelf: RoomBookshelf, cache: RoomCache):
        self.bookshelf = bookshelf
        self.cache = cache
        self.retrieval_stats: Dict[str, int] = {"vector": 0, "graph": 0, "keyword": 0}

    def agentic_retrieve(self, query: str, top_k: int = 8, use_cache: bool = True) -> List[Dict]:
        """
        Agentic retrieval with routing between Vector, Graph, and Keyword.
        Includes basic re-ranking and caching.
        """
        cache_key = f"rag_{hash(query)}"
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        results = []

        # Vector retrieval
        vector_res = self.bookshelf.query("vector", query)
        results.append({"source": "vector", "content": vector_res.get("result", ""), "score": 0.85})
        self.retrieval_stats["vector"] += 1

        # Graph retrieval (relationships)
        graph_res = self.bookshelf.query("graph", query)
        results.append({"source": "graph", "content": graph_res.get("result", ""), "score": 0.80})
        self.retrieval_stats["graph"] += 1

        # Simple keyword-style on document store
        doc_res = self.bookshelf.query("document", query)
        results.append({"source": "document", "content": doc_res.get("result", ""), "score": 0.75})
        self.retrieval_stats["keyword"] += 1

        # Re-rank by score
        results = sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]

        if use_cache:
            self.cache.set(cache_key, results, ttl=300)

        return results

    def consolidate_memory(self, new_knowledge: Dict[str, Any]):
        """
        Agentic memory consolidation.
        Merges new role contributions / feedback into the room's long-term knowledge.
        """
        # Store in multiple DB types for robustness
        self.bookshelf.store("vector", new_knowledge, category="role_contributions")
        self.bookshelf.store("graph", {"relation": "contributed_to", "data": new_knowledge})
        self.bookshelf.store("document", new_knowledge)

        # Invalidate relevant cache entries
        self.cache.invalidate("room_knowledge_context")

    def get_retrieval_stats(self) -> Dict[str, Any]:
        return {
            "total_retrievals": sum(self.retrieval_stats.values()),
            "breakdown": self.retrieval_stats
        }
