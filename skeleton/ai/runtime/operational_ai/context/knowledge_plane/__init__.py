"""Source-bound, revisioned, owner-scoped local knowledge for the native AI.

The API never promotes source text into system instructions, nor treats a
citation identifier as a truth guarantee. Import is an explicit operator action.
"""

from .service import KnowledgePlane
from .provider import KnowledgeEvidenceProvider
from .contracts import KnowledgeError, KnowledgePolicy, DocumentRecord, SearchResult

__all__ = ["KnowledgePlane", "KnowledgeEvidenceProvider", "KnowledgeError",
           "KnowledgePolicy", "DocumentRecord", "SearchResult"]
