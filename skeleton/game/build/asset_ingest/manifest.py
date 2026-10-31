"""Content-hashed asset manifest with duplicate collapsing.

Each unique content blob is stored once under its ContentAddress; every path
that carried the same bytes becomes an alias of the canonical entry.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from skeleton.game.build.flgb_build_runtime import ContentAddress, dig

from .importers import AssetImportError, ImportedAsset

MANIFEST_SCHEMA = "skeleton.game.asset_manifest.v1"
NAMESPACE = "game-assets"


@dataclass
class ManifestEntry:
    sha256: str
    kind: str
    format: str
    size: int
    path: str  # canonical (lexicographically first) path
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    receipt_digest: str = ""

    @property
    def address(self) -> str:
        return ContentAddress(NAMESPACE, "sha256", self.sha256).uri

    def to_dict(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "address": self.address, "kind": self.kind, "format": self.format,
                "size": self.size, "path": self.path, "aliases": sorted(self.aliases),
                "metadata": self.metadata, "receipt_digest": self.receipt_digest}


class AssetManifest:
    def __init__(self) -> None:
        self._entries: dict[str, ManifestEntry] = {}
        self._paths: dict[str, str] = {}

    def add(self, asset: ImportedAsset) -> bool:
        """Add an asset; return False when its bytes were already present (a duplicate)."""
        prior = self._paths.get(asset.path)
        if prior is not None and prior != asset.sha256:
            raise AssetImportError(f"path {asset.path} already maps to different content")
        if prior is not None:
            return False
        self._paths[asset.path] = asset.sha256
        entry = self._entries.get(asset.sha256)
        if entry is None:
            self._entries[asset.sha256] = ManifestEntry(
                asset.sha256, asset.kind, asset.format, asset.size, asset.path,
                metadata=asset.metadata, receipt_digest=asset.receipt().digest)
            return True
        if asset.kind != entry.kind:
            raise AssetImportError(f"{asset.path} duplicates {entry.path} but as a different kind")
        if asset.path < entry.path:
            entry.aliases.append(entry.path)
            entry.path = asset.path
        else:
            entry.aliases.append(asset.path)
        return False

    def resolve(self, path: str) -> ManifestEntry:
        try:
            return self._entries[self._paths[path]]
        except KeyError as exc:
            raise AssetImportError(f"asset not in manifest: {path}") from exc

    @property
    def entries(self) -> list[ManifestEntry]:
        return sorted(self._entries.values(), key=lambda e: e.path)

    def duplicates(self) -> dict[str, list[str]]:
        return {e.path: sorted(e.aliases) for e in self.entries if e.aliases}

    def to_dict(self) -> dict[str, Any]:
        entries = [e.to_dict() for e in self.entries]
        return {"schema": MANIFEST_SCHEMA, "entries": entries, "digest": dig(entries),
                "unique_bytes": sum(e.size for e in self._entries.values()),
                "paths": len(self._paths)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> AssetManifest:
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            raise AssetImportError("manifest is not json") from exc
        if not isinstance(doc, dict) or doc.get("schema") != MANIFEST_SCHEMA:
            raise AssetImportError("unsupported manifest schema")
        if dig(doc.get("entries")) != doc.get("digest"):
            raise AssetImportError("manifest digest mismatch")
        m = cls()
        for e in doc["entries"]:
            entry = ManifestEntry(e["sha256"], e["kind"], e["format"], e["size"], e["path"],
                                  list(e["aliases"]), e["metadata"], e["receipt_digest"])
            m._entries[entry.sha256] = entry
            for p in [entry.path, *entry.aliases]:
                m._paths[p] = entry.sha256
        return m
