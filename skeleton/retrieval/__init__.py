"""Quad retrieval subsystem for Skeleton."""

from .fusion import Fuser, FusionStrategy, ScoredResult
from .ranking import Ranker
from .query import QueryPlan, QueryPlanner, RetrievalError
from .index import InvertedIndex
from .query_language import QueryParser, QueryTerm
from .cache import CacheEntry, ResultCache
from .chunking import Chunk, Chunker
from .sources import SourceRegistry
from .ingest import CorpusIngestor, Document
from .rerank import Reranker, RerankRule
from .highlight import Highlighter
from .dedup import Deduper
from .embeddings import LocalEmbedder, rerank_by_embedding
from .lexicon import Lexicon, default_lexicon

__all__ = [
    "Fuser",
    "FusionStrategy",
    "ScoredResult",
    "Ranker",
    "QueryPlan",
    "QueryPlanner",
    "RetrievalError",
    "InvertedIndex",
    "QueryParser",
    "QueryTerm",
    "CacheEntry",
    "ResultCache",
    "Chunk",
    "Chunker",
    "SourceRegistry",
    "CorpusIngestor",
    "Document",
    "Reranker",
    "RerankRule",
    "Highlighter",
    "Deduper",
    "LocalEmbedder",
    "rerank_by_embedding",
    "Lexicon",
    "default_lexicon",
]
