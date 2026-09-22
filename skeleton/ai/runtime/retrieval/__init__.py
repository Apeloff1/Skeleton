"""
Skeleton Retrieval Package

Exports:
- Fuser / FusionStrategy / ScoredResult: Multi-plane fusion
- Ranker: Blended score ordering
- FeatureReranker: Learned re-ranking
- ProvenanceLedger: Data lineage
- QuadRetriever: Four-plane unified search (self-populating KAG)
- KnowledgeGraph / KAGRetriever / Triple: Knowledge plane
- TripleExtractor: Rule-based fact extraction
"""

from skeleton.retrieval.fusion import FusionStrategy, Fuser, ScoredResult
from skeleton.retrieval.ranking import Ranker
from skeleton.retrieval.reranker import FeatureReranker
from skeleton.retrieval.provenance import ProvenanceEntry, ProvenanceLedger
from skeleton.retrieval.quad import PlaneResult, QuadRetriever
from skeleton.retrieval.kag import KAGRetriever, KnowledgeGraph, Triple
from skeleton.retrieval.extraction import TripleExtractor

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
    "TripleExtractor",
]
