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
from skeleton.retrieval.jvm_fusion_accelerator import (
    FusionAcceleratorStatus,
    FusionHit,
    JvmFusionAccelerator,
    JvmFusionConfig,
    JvmFusionError,
    JvmFusionProtocolError,
    JvmFusionTimeout,
    JvmFusionUnavailable,
    close_default_fusion_accelerator,
    get_default_fusion_accelerator,
)
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
    "FusionAcceleratorStatus",
    "FusionHit",
    "JvmFusionAccelerator",
    "JvmFusionConfig",
    "JvmFusionError",
    "JvmFusionUnavailable",
    "JvmFusionProtocolError",
    "JvmFusionTimeout",
    "get_default_fusion_accelerator",
    "close_default_fusion_accelerator",
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
