"""Content-hashed asset manifest with duplicate collapsing.

Each unique content blob is stored once under its ContentAddress; every path
that carried the same bytes becomes an alias of the canonical entry.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import PurePosixPath
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


MAX_MANIFEST_ENTRIES = 8192
MAX_MANIFEST_JSON_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_TOTAL_BYTES = 512 * 1024 * 1024

MAX_MANIFEST_JSON_DEPTH = 64
MAX_MANIFEST_JSON_NODES = 131072


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AssetImportError("manifest duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite_json(token: str) -> Any:
    raise AssetImportError(f"manifest nonfinite JSON number: {token}")


def _bound_json_structure(root: Any) -> None:
    """Bound attacker-controlled nesting and node count before hashing."""
    pending = [(root, 0)]
    seen = 0
    while pending:
        node, depth = pending.pop()
        seen += 1
        if depth > MAX_MANIFEST_JSON_DEPTH or seen > MAX_MANIFEST_JSON_NODES:
            raise AssetImportError("manifest JSON structure exceeds bound")
        if type(node) is dict:
            pending.extend((value, depth + 1) for value in node.values())
        elif type(node) is list:
            pending.extend((value, depth + 1) for value in node)



def _valid_path(path: object) -> bool:
    if type(path) is not str or not path or len(path) > 4096:
        return False
    if any(char in path for char in (chr(92), chr(0), ":", "%", "?", "#")):
        return False
    if any(unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in path):
        return False
    parts = path.split("/")
    return (len(parts) <= 32 and all(part not in ("", ".", "..") for part in parts)
            and not PurePosixPath(path).is_absolute())


class AssetManifest:
    def __init__(self) -> None:
        self._entries: dict[str, ManifestEntry] = {}
        self._paths: dict[str, str] = {}

    def add(self, asset: ImportedAsset) -> bool:
        """Atomically bind a validated asset path to its content address."""
        if not isinstance(asset, ImportedAsset) or not _valid_path(asset.path):
            raise AssetImportError("invalid manifest asset path")
        prior = self._paths.get(asset.path)
        if prior is not None and prior != asset.sha256:
            raise AssetImportError(f"path {asset.path} already maps to different content")
        if prior is not None:
            return False
        entry = self._entries.get(asset.sha256)
        if entry is not None and (
            asset.kind != entry.kind or asset.format != entry.format
            or asset.size != entry.size or asset.metadata != entry.metadata
        ):
            raise AssetImportError(f"{asset.path} duplicates {entry.path} with incompatible metadata")
        # All validation and receipt computation must finish before mutation.
        receipt = asset.receipt().digest
        if entry is None:
            new_entry = ManifestEntry(
                asset.sha256, asset.kind, asset.format, asset.size, asset.path,
                metadata=asset.metadata, receipt_digest=receipt,
            )
            self._entries[asset.sha256] = new_entry
            self._paths[asset.path] = asset.sha256
            return True
        if asset.path < entry.path:
            entry.aliases.append(entry.path)
            entry.path = asset.path
            entry.receipt_digest = receipt
        else:
            entry.aliases.append(asset.path)
        self._paths[asset.path] = asset.sha256
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
        """Restore only canonical, bounded, collision-free manifest evidence."""
        if type(raw) is not str:
            raise AssetImportError("manifest input must be text")
        try:
            size = len(raw.encode("utf-8"))
        except UnicodeError as exc:
            raise AssetImportError("manifest is not utf-8") from exc
        if size > MAX_MANIFEST_JSON_BYTES:
            raise AssetImportError("manifest exceeds input bound")
        try:
            doc = json.loads(raw, object_pairs_hook=_unique_json_object,
                             parse_constant=_reject_nonfinite_json)
        except AssetImportError:
            raise
        except (ValueError, RecursionError) as exc:
            raise AssetImportError("manifest is not strict json") from exc
        _bound_json_structure(doc)
        if type(doc) is not dict or doc.get("schema") != MANIFEST_SCHEMA:
            raise AssetImportError("unsupported manifest schema")
        entries = doc.get("entries")
        if type(entries) is not list or len(entries) > MAX_MANIFEST_ENTRIES:
            raise AssetImportError("manifest entries exceed bound")
        if dig(entries) != doc.get("digest"):
            raise AssetImportError("manifest digest mismatch")
        m = cls()
        all_paths: set[str] = set()
        total_bytes = 0
        required = {"sha256", "address", "kind", "format", "size", "path",
                    "aliases", "metadata", "receipt_digest"}
        for item in entries:
            if type(item) is not dict or set(item) != required:
                raise AssetImportError("manifest entry shape mismatch")
            sha, path, aliases = item["sha256"], item["path"], item["aliases"]
            if (type(sha) is not str or len(sha) != 64
                    or any(ch not in "0123456789abcdef" for ch in sha)
                    or sha in m._entries):
                raise AssetImportError("manifest content identity invalid or duplicated")
            if (not _valid_path(path) or type(aliases) is not list
                    or any(not _valid_path(alias) for alias in aliases)
                    or aliases != sorted(set(aliases))
                    or (aliases and path >= aliases[0])):
                raise AssetImportError("manifest canonical path or aliases invalid")
            if any(name in all_paths for name in (path, *aliases)):
                raise AssetImportError("manifest path aliases collide")
            kind, fmt, size, metadata = (item["kind"], item["format"],
                                         item["size"], item["metadata"])
            if (kind not in ("texture", "mesh", "audio") or type(fmt) is not str
                    or not fmt or type(size) is not int or size < 1
                    or size > 256 * 1024 * 1024 or type(metadata) is not dict):
                raise AssetImportError("manifest entry metadata invalid")
            entry = ManifestEntry(sha, kind, fmt, size, path, list(aliases),
                                  metadata, item["receipt_digest"])
            if item["address"] != entry.address:
                raise AssetImportError("manifest content address mismatch")
            expected_receipt = ImportedAsset(path, kind, fmt, size, sha, metadata).receipt().digest
            if entry.receipt_digest != expected_receipt:
                raise AssetImportError("manifest receipt identity mismatch")
            m._entries[sha] = entry
            for name in (path, *aliases):
                m._paths[name] = sha
                all_paths.add(name)
            if len(all_paths) > MAX_MANIFEST_ENTRIES:
                raise AssetImportError("manifest path count exceeds bound")
            total_bytes += size
            if total_bytes > MAX_MANIFEST_TOTAL_BYTES:
                raise AssetImportError("manifest aggregate bytes exceed bound")
        if doc != m.to_dict():
            raise AssetImportError("manifest summary or canonical ordering mismatch")
        return m
