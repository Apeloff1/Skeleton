"""
Skeleton Retrieval Package

Exports:
- Fuser: Multi-plane result fusion
- FusionStrategy: RRF, weighted, confidence, first
- ScoredResult: Typed retrieval result
- Ranker: Feature-based re-ranking
"""

from skeleton.retrieval.fusion import (
    FusionStrategy,
    Fuser,
    Ranker,
    ScoredResult,
)

__all__ = [
    "Fuser",
    "FusionStrategy",
    "ScoredResult",
    "Ranker",
]
