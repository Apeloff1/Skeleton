"""Policy-bound webcrawler plane for AI information gathering."""

from .core import (
    CrawlBudget, CrawlDocument, CrawlEngine, CrawlPolicy, FrontierItem,
    InMemoryCrawlStore, canonicalize_url, extract_document,
)
from .context_bridge import CrawlContextBundle, compile_crawl_context
from .retrieval_bridge import (
    CrawlRetrievalBridgeError, CrawlRetrievalRecord, bridge_crawl_document,
)

__all__ = [
    "CrawlBudget", "CrawlDocument", "CrawlEngine", "CrawlPolicy",
    "FrontierItem", "InMemoryCrawlStore", "canonicalize_url", "extract_document",
    "CrawlRetrievalBridgeError", "CrawlRetrievalRecord", "bridge_crawl_document",
    "CrawlContextBundle", "compile_crawl_context",
]
