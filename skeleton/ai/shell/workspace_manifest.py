"""Deterministic workspace/source manifests for review-to-execution preconditions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json


class WorkspaceEntryKind(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


@dataclass(frozen=True)
class WorkspaceEntry:
    path: str
    kind: WorkspaceEntryKind
    digest: str
    size_bytes: int = 0
    mode: int | None = None

    def __post_init__(self) -> None:
        if not self.path or len(self.path) > 4096:
            raise ValueError("invalid workspace entry path")
        object.__setattr__(self, "kind", WorkspaceEntryKind(self.kind))
        if len(self.digest) != 64:
            raise ValueError("workspace entry digest must be SHA-256 hex")
        if self.size_bytes < 0:
            raise ValueError("workspace entry size may not be negative")
        if self.mode is not None and self.mode < 0:
            raise ValueError("workspace entry mode may not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind.value,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class WorkspaceManifest:
    manifest_id: str
    entries: tuple[WorkspaceEntry, ...]
    root_label: str = ""

    def __post_init__(self) -> None:
        if not self.manifest_id or len(self.manifest_id) > 160:
            raise ValueError("invalid workspace manifest_id")
        entries = tuple(sorted(self.entries, key=lambda item: item.path))
        paths = [item.path for item in entries]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate workspace entry path")
        object.__setattr__(self, "entries", entries)

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_id": self.manifest_id,
            "root_label": self.root_label,
            "entries": [item.to_dict() for item in self.entries],
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class WorkspaceDrift:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def to_dict(self) -> dict[str, object]:
        return {
            "clean": self.clean,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
        }


class WorkspaceManifestComparator:
    def compare(
        self,
        expected: WorkspaceManifest,
        observed: WorkspaceManifest,
    ) -> WorkspaceDrift:
        left = {item.path: item for item in expected.entries}
        right = {item.path: item for item in observed.entries}
        added = tuple(sorted(right.keys() - left.keys()))
        removed = tuple(sorted(left.keys() - right.keys()))
        changed = tuple(
            sorted(
                path
                for path in left.keys() & right.keys()
                if left[path] != right[path]
            )
        )
        return WorkspaceDrift(added, removed, changed)
