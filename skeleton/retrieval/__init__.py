"""Retrieval subsystem — search pipeline + primitives re-exported."""

from .cache import CacheEntry, ResultCache
from .chunking import Chunk, Chunker
from .dedup import Deduper
from .embeddings import LocalEmbedder, rerank_by_embedding
from .fusion import Fuser, FusionStrategy, ScoredResult
from .highlight import Highlighter
from .index import InvertedIndex
from .ingest import CorpusIngestor, Document
from .lexicon import Lexicon, default_lexicon
from .pipeline import SearchOutcome, SearchPipeline
from .plane_weights import PlaneArm, PlaneWeightLearner
from .quad import Fragment, KnowledgeEdge, QuadRetriever
from .query import QueryPlan, QueryPlanner, RetrievalError
from .query_language import QueryParser, QueryTerm
from .ranking import Ranker
from .rerank import Reranker, RerankRule
from .reranker import FeatureReranker
from .suggest import Suggester
from .sources import SourceRegistry
from .ui import ResultRenderer

__all__ = [
    "CacheEntry",
    "ResultCache",
    "Chunk",
    "Chunker",
    "Deduper",
    "LocalEmbedder",
    "rerank_by_embedding",
    "Fuser",
    "FusionStrategy",
    "ScoredResult",
    "Highlighter",
    "InvertedIndex",
    "CorpusIngestor",
    "Document",
    "Lexicon",
    "default_lexicon",
    "SearchOutcome",
    "SearchPipeline",
    "PlaneArm",
    "PlaneWeightLearner",
    "Fragment",
    "KnowledgeEdge",
    "QuadRetriever",
    "QueryPlan",
    "QueryPlanner",
    "RetrievalError",
    "QueryParser",
    "QueryTerm",
    "Ranker",
    "Reranker",
    "RerankRule",
    "FeatureReranker",
    "Suggester",
    "SourceRegistry",
    "ResultRenderer",
]
