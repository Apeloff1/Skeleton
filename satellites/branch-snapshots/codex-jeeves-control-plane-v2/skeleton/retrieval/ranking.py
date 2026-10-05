"""
Skeleton Retrieval — Ranking module

Provides:
- Ranker: Score-based result ordering with diversity and recency boosts
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class Ranker:
    """Order retrieval results by blended score signals.

    Blends:
    - relevance: base retrieval score
    - recency: newer documents rank higher
    - diversity: avoid duplicate-near results
    """

    def __init__(self, recency_weight: float = 0.2, diversity_weight: float = 0.1):
        self.recency_weight = recency_weight
        self.diversity_weight = diversity_weight
        self._ranked = 0

    def rank(self, results: List[Any], top_k: Optional[int] = None) -> List[Any]:
        """Rank results by blended score."""
        if not results:
            return []
        self._ranked += len(results)
        now = time.time()

        scored = []
        seen_content: set = set()
        for r in results:
            base = getattr(r, "score", 0.5)
            ts = getattr(r, "metadata", {}).get("timestamp", now) if hasattr(r, "metadata") else now
            age_hours = max(0.0, (now - ts) / 3600.0)
            recency = 1.0 / (1.0 + age_hours / 24.0)

            content = getattr(r, "content", "") or getattr(getattr(r, "chunk", None), "text", "")
            sig = content[:64]
            diversity = 0.0 if sig in seen_content else 1.0
            seen_content.add(sig)

            blended = base + self.recency_weight * recency + self.diversity_weight * diversity
            scored.append((blended, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = [r for _, r in scored]
        return ranked[:top_k] if top_k else ranked

    def stats(self) -> Dict[str, Any]:
        return {"ranked": self._ranked}
