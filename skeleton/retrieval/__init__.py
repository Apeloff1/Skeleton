"""
Skeleton Retrieval Package

Exports:
- Fuser / FusionStrategy / ScoredResult: Multi-plane fusion
- Ranker: Blended score ordering
- FeatureReranker: Learned re-ranking
- ProvenanceLedger: Data lineage
- QuadRetriever: Four-plane unified search
- KnowledgeGraph / KAGRetriever: Knowledge plane
"""

from skeleton.retrieval.fusion import FusionStrategy, Fuser, ScoredResult
from skeleton.retrieval.ranking import Ranker
from skeleton.retrieval.reranker import FeatureReranker
from skeleton.retrieval.provenance import ProvenanceEntry, ProvenanceLedger
from skeleton.retrieval.quad import PlaneResult, QuadRetriever
from skeleton.retrieval.kag import KAGRetriever, KnowledgeGraph, Triple

__all__ = [
    "Fuser",
    "FusionStrategy",
    "ScoredResult",
    "Ranker",
    "FeatureReranker",
    "ProvenanceLedger",
    "ProvenanceEntry",
    "QuadRetriever",
    "PlaneResult",
    "KnowledgeGraph",
    "KAGRetriever",
    "Triple",
]
