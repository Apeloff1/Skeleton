#!/usr/bin/env python3
"""
Hybrid RAG Wiring for Zaibatsu CNS
Wires Vector + Graph + Keyword retrieval on top of the new indexes and Bookshelf.
"""

from typing import List, Dict, Any
import json

class HybridRAGWiring:
    def __init__(self, category_index_path: str, role_graph_path: str):
        self.category_index = self._load_json(category_index_path)
        self.role_graph = self._load_json(role_graph_path)
        self.vector_index = {}
        self.graph_index = self.role_graph  # NetworkX or similar

    def _load_json(self, path: str) -> Dict:
        with open(path, "r") as f:
            return json.load(f)

    def retrieve(self, query: str, room_id: str, top_k: int = 10) -> List[Dict]:
        """
        Hybrid retrieval: Vector + Graph + Keyword + Category synergy.
        """
        results = []
        
        # 1. Keyword + Category lookup
        keyword_results = self._keyword_category_lookup(query, room_id)
        
        # 2. Vector similarity (placeholder)
        vector_results = self._vector_similarity(query, room_id)
        
        # 3. Graph traversal for synergy
        graph_results = self._graph_synergy_traversal(query, room_id)
        
        # Merge + re-rank with coherence score
        merged = self._merge_and_rerank(keyword_results, vector_results, graph_results)
        
        return merged[:top_k]

    def _keyword_category_lookup(self, query: str, room_id: str) -> List[Dict]:
        terms = {part.lower() for part in query.split() if part}
        hits = []
        rooms = self.category_index.get(room_id, self.category_index)
        if isinstance(rooms, dict):
            for key, value in rooms.items():
                blob = f"{key} {value}".lower()
                overlap = [term for term in terms if term in blob]
                if overlap:
                    hits.append({"id": str(key), "lane": "keyword", "score": len(overlap), "room": room_id})
        return hits

    def _vector_similarity(self, query: str, room_id: str) -> List[Dict]:
        import hashlib
        def vec(text: str):
            buckets = [0.0] * 16
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode()).digest()
                buckets[digest[0] % 16] += 1.0
            norm = sum(x * x for x in buckets) ** 0.5 or 1.0
            return [x / norm for x in buckets]
        q = vec(query)
        hits = []
        rooms = self.category_index.get(room_id, self.category_index)
        if isinstance(rooms, dict):
            for key, value in rooms.items():
                score = sum(a * b for a, b in zip(q, vec(f"{key} {value}")))
                if score > 0:
                    hits.append({"id": str(key), "lane": "vector", "score": score, "room": room_id})
        return hits

    def _graph_synergy_traversal(self, query: str, room_id: str) -> List[Dict]:
        hits = []
        graph = self.role_graph if isinstance(self.role_graph, dict) else {}
        for source, targets in graph.items():
            names = targets if isinstance(targets, list) else [targets]
            if room_id == source or query.lower() in str(source).lower():
                for target in names:
                    hits.append({"id": str(target), "lane": "graph", "score": 1.0, "room": room_id})
        return hits

    def _merge_and_rerank(self, *result_lists) -> List[Dict]:
        pooled = {}
        for bucket in result_lists:
            for row in bucket:
                current = pooled.setdefault(row["id"], {"id": row["id"], "score": 0.0, "lanes": [], "room": row.get("room")})
                current["score"] += float(row.get("score", 0))
                current["lanes"].append(row.get("lane"))
        return sorted(pooled.values(), key=lambda item: item["score"], reverse=True)

if __name__ == "__main__":
    rag = HybridRAGWiring(
        "/home/workdir/artifacts/gameforge_v1/gameforge/indexes/master_category_index.json",
        "/home/workdir/artifacts/gameforge_v1/gameforge/graph/role_contribution_graph.json"
    )
    print("Hybrid RAG Wiring initialized and ready.")
