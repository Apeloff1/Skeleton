"""Research evidence and historical lineage; this namespace grants no production authority."""

from .source_lineage import (
    CitationEdge,
    CitationGraphReport,
    CitationRelation,
    CitationSpec,
    HistoricalTechnique,
    IngestionReceipt,
    ReplicationOutcome,
    ReplicationRecord,
    ResearchClaim,
    ResearchLineageError,
    ResearchSource,
    ResearchSourceRegistry,
    RetractionRecord,
    SourceStatus,
    content_digest,
)

__all__ = [
    "CitationEdge",
    "CitationGraphReport",
    "CitationRelation",
    "CitationSpec",
    "HistoricalTechnique",
    "IngestionReceipt",
    "ReplicationOutcome",
    "ReplicationRecord",
    "ResearchClaim",
    "ResearchLineageError",
    "ResearchSource",
    "ResearchSourceRegistry",
    "RetractionRecord",
    "SourceStatus",
    "content_digest",
]
