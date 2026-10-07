"""
Skeleton Retrieval — Ranking module

Provides:
- Ranker: Score-based result ordering with diversity and recency boosts
"""

from __future__ import annotations

import math
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
        if isinstance(recency_weight, bool) or not isinstance(recency_weight, (int, float)) or float(recency_weight) < 0:
            raise ValueError("recency weight must be non-negative")
        if isinstance(diversity_weight, bool) or not isinstance(diversity_weight, (int, float)) or float(diversity_weight) < 0:
            raise ValueError("diversity weight must be non-negative")
        self.recency_weight = float(recency_weight)
        self.diversity_weight = float(diversity_weight)
        self._ranked = 0

    def rank(self, results: List[Any], top_k: Optional[int] = None) -> List[Any]:
        """Rank results by blended score."""
        if not results:
            return []
        self._ranked += len(results)
        now = time.time()

        prelim = []
        for r in results:
            if not hasattr(r, "score"):
                raise ValueError("result score is required")
            base = r.score
            if isinstance(base, bool) or not isinstance(base, (int, float)) or not math.isfinite(float(base)):
                raise ValueError("result score must be finite")
            metadata = getattr(r, "metadata", None)
            if isinstance(metadata, dict) and "timestamp" in metadata:
                raw_ts = metadata["timestamp"]
                if isinstance(raw_ts, bool) or not isinstance(raw_ts, (int, float)) or not math.isfinite(float(raw_ts)):
                    raise ValueError("timestamp must be finite")
                age_hours = max(0.0, (now - float(raw_ts)) / 3600.0)
                recency = 1.0 / (1.0 + age_hours / 24.0)
            else:
                recency = 0.0
            content = getattr(r, "content", "") or getattr(getattr(r, "chunk", None), "text", "")
            if not isinstance(content, str):
                content = str(content or "")
            prelim.append((base + self.recency_weight * recency, content[:64], r))

        # Diversity belongs to the stronger copy, not whichever duplicate
        # happened to sit earlier in the input.
        prelim.sort(key=lambda item: item[0], reverse=True)
        seen_content: set = set()
        scored = []
        for base, sig, r in prelim:
            diversity = 0.0 if sig in seen_content else 1.0
            seen_content.add(sig)
            scored.append((base + self.diversity_weight * diversity, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = [r for _, r in scored]
        if top_k is None:
            return ranked
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
            raise ValueError("top_k must be a non-negative integer or None")
        return ranked[:top_k]

    def stats(self) -> Dict[str, Any]:
        return {"ranked": self._ranked}
