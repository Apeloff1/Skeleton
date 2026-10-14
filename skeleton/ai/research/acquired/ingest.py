"""
Skeleton Acquired — Asset ingestion and management

Provides:
- AssetIngestor: Ingest external assets (images, audio, models)
- AssetLibrary: Catalog and retrieve assets
- AssetValidator: Validate asset integrity and format
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class Asset:
    """A managed asset with metadata."""
    asset_id: str
    name: str
    asset_type: str  # image, audio, model, texture, animation
    source_path: str
    checksum: str
    size_bytes: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    ingested_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "type": self.asset_type,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum[:16] + "...",
            "tags": self.tags,
            "metadata": self.metadata,
        }


class AssetValidator:
    """Validate asset integrity and format."""

    SUPPORTED_FORMATS = {
        "image": ["png", "jpg", "jpeg", "webp", "tga"],
        "audio": ["wav", "ogg", "mp3"],
        "model": ["obj", "fbx", "gltf", "glb"],
        "texture": ["png", "dds", "ktx"],
        "animation": ["fbx", "gltf"],
    }

    def validate(self, path: str, asset_type: str) -> Dict[str, Any]:
        """Validate an asset file."""
        p = Path(path)
        
        if not p.exists():
            return {"valid": False, "error": "file_not_found"}
        
        ext = p.suffix.lower().lstrip(".")
        supported = self.SUPPORTED_FORMATS.get(asset_type, [])
        
        if ext not in supported:
            return {"valid": False, "error": f"unsupported_format: {ext}", "supported": supported}
        
        # Compute checksum
        try:
            with open(p, "rb") as f:
                checksum = hashlib.blake2b(f.read(), digest_size=32).hexdigest()
        except Exception as e:
            return {"valid": False, "error": str(e)}
        
        return {
            "valid": True,
            "checksum": checksum,
            "size_bytes": p.stat().st_size,
            "format": ext,
        }


class AssetLibrary:
    """Catalog and retrieve managed assets."""

    def __init__(self, storage_path: Optional[Path] = None, bus: Optional[EventBus] = None):
        self._assets: Dict[str, Asset] = {}
        self._by_type: Dict[str, List[str]] = {}
        self._by_tag: Dict[str, List[str]] = {}
        self._storage = storage_path or Path("assets")
        self._bus = bus
        self._validator = AssetValidator()
        self._stats = {"ingested": 0, "retrieved": 0}

    def ingest(self, path: str, name: str, asset_type: str, tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ingest an asset into the library."""
        validation = self._validator.validate(path, asset_type)
        if not validation["valid"]:
            return validation
        
        import uuid
        asset = Asset(
            asset_id=str(uuid.uuid4())[:12],
            name=name,
            asset_type=asset_type,
            source_path=path,
            checksum=validation["checksum"],
            size_bytes=validation["size_bytes"],
            metadata=metadata or {},
            tags=tags or [],
        )
        
        self._assets[asset.asset_id] = asset
        self._by_type.setdefault(asset_type, []).append(asset.asset_id)
        
        for tag in (tags or []):
            self._by_tag.setdefault(tag, []).append(asset.asset_id)
        
        self._stats["ingested"] += 1
        
        if self._bus:
            self._bus.emit("acquired.asset.ingested", {
                "asset_id": asset.asset_id,
                "name": name,
                "type": asset_type,
            })
        
        return {"valid": True, "asset_id": asset.asset_id, "asset": asset.to_dict()}

    def get(self, asset_id: str) -> Optional[Asset]:
        """Retrieve an asset by ID."""
        self._stats["retrieved"] += 1
        return self._assets.get(asset_id)

    def find(self, asset_type: Optional[str] = None, tag: Optional[str] = None) -> List[Asset]:
        """Find assets by type or tag."""
        results = set()
        
        if asset_type:
            results.update(self._by_type.get(asset_type, []))
        
        if tag:
            tag_results = set(self._by_tag.get(tag, []))
            if results:
                results &= tag_results
            else:
                results = tag_results
        
        return [self._assets[aid] for aid in results if aid in self._assets]

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "total": len(self._assets),
            "by_type": {t: len(aids) for t, aids in self._by_type.items()},
        }


class AssetIngestor:
    """Batch asset ingestion pipeline."""

    def __init__(self, library: AssetLibrary, bus: Optional[EventBus] = None):
        self._library = library
        self._bus = bus
        self._batch_queue: List[Dict[str, Any]] = []

    def queue(self, path: str, name: str, asset_type: str, **kwargs) -> None:
        """Queue an asset for batch ingestion."""
        self._batch_queue.append({
            "path": path,
            "name": name,
            "asset_type": asset_type,
            **kwargs,
        })

    def process_batch(self) -> Dict[str, Any]:
        """Process all queued assets."""
        results = []
        for item in self._batch_queue:
            result = self._library.ingest(
                path=item["path"],
                name=item["name"],
                asset_type=item["asset_type"],
                tags=item.get("tags"),
                metadata=item.get("metadata"),
            )
            results.append(result)
        
        self._batch_queue.clear()
        
        successful = sum(1 for r in results if r.get("valid"))
        failed = len(results) - successful
        
        return {
            "processed": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

    def stats(self) -> Dict[str, Any]:
        return {"queued": len(self._batch_queue)}
