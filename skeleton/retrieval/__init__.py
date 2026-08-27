"""Retrieval subsystem — query, fuse, rank, ingest, suggest, uptime-aware lexicon."""

from .cache import CacheEntry, ResultCache
from .chunking import Chunk, Chunker
from .dedup import Deduper
from .embeddings import LocalEmbedder, rerank_by_embedding
from .fusion import Fuser, FusionStrategy, ScoredResult
from .highlight import Highlighter
from .index import InvertedIndex
from .ingest import CorpusIngestor, Document
from .lexicon import Lexicon, default_lexicon
from .query import QueryPlan, QueryPlanner, RetrievalError
from .query_language import QueryParser, QueryTerm
from .ranking import Ranker
from .rerank import Reranker, RerankRule
from .suggest import Suggester
from .sources import SourceRegistry

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
    "QueryPlan",
    "QueryPlanner",
    "RetrievalError",
    "QueryParser",
    "QueryTerm",
    "Ranker",
    "Reranker",
    "RerankRule",
    "Suggester",
    "SourceRegistry",
]
