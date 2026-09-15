"""
Skeleton Acquired Package

Exports:
- AssetIngestor: Batch asset ingestion
- AssetLibrary: Asset catalog
- AssetValidator: Format validation
- Asset: Asset data type
"""

from skeleton.acquired.ingest import (
    Asset,
    AssetIngestor,
    AssetLibrary,
    AssetValidator,
)

__all__ = [
    "AssetIngestor",
    "AssetLibrary",
    "AssetValidator",
    "Asset",
]
