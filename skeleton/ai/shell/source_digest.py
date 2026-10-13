"""Safe source/workspace digest provider for execution preconditions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

from skeleton.shells.ai.workspace_manifest import (
    WorkspaceEntry,
    WorkspaceEntryKind,
    WorkspaceManifest,
)


@dataclass(frozen=True)
class SourceDigestPolicy:
    root: Path
    max_file_bytes: int = 16 * 1024 * 1024
    max_manifest_entries: int = 10000
    max_manifest_bytes: int = 256 * 1024 * 1024
    allow_symlinks: bool = False

    def __post_init__(self) -> None:
        root = Path(self.root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("source digest root must be a directory")
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if self.max_manifest_entries <= 0:
            raise ValueError("max_manifest_entries must be positive")
        if self.max_manifest_bytes <= 0:
            raise ValueError("max_manifest_bytes must be positive")
        object.__setattr__(self, "root", root)


class SourceDigestError(RuntimeError):
    pass


class SourceDigestProvider:
    """Hash files beneath one fixed root without following unapproved symlinks."""

    def __init__(self, policy: SourceDigestPolicy) -> None:
        self.policy = policy

    def _candidate(self, resource_id: str) -> Path:
        if not resource_id or len(resource_id) > 4096:
            raise ValueError("invalid source resource_id")
        raw = Path(resource_id)
        if raw.is_absolute():
            raise SourceDigestError("source resource_id must be relative")
        candidate = self.policy.root / raw
        try:
            relative_parts = candidate.relative_to(self.policy.root).parts
        except ValueError as exc:
            raise SourceDigestError("source resource escapes configured root") from exc
        current = self.policy.root
        for part in relative_parts:
            current = current / part
            if current.is_symlink() and not self.policy.allow_symlinks:
                raise SourceDigestError("source symlink is not permitted")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise SourceDigestError("source resource does not exist") from exc
        try:
            resolved.relative_to(self.policy.root)
        except ValueError as exc:
            raise SourceDigestError("resolved source escapes configured root") from exc
        return resolved

    def digest(self, resource_id: str) -> str:
        path = self._candidate(resource_id)
        if not path.is_file():
            raise SourceDigestError("source resource is not a regular file")
        size = path.stat().st_size
        if size > self.policy.max_file_bytes:
            raise SourceDigestError("source file exceeds digest byte limit")
        digest = hashlib.sha256()
        read = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                read += len(chunk)
                if read > self.policy.max_file_bytes:
                    raise SourceDigestError("source file exceeded digest byte limit while reading")
                digest.update(chunk)
        return digest.hexdigest()

    def __call__(self, resource_id: str) -> str:
        return self.digest(resource_id)

    def entry(self, resource_id: str) -> WorkspaceEntry:
        path = self._candidate(resource_id)
        if not path.is_file():
            raise SourceDigestError("manifest entry must be a regular file")
        stat = path.stat()
        if stat.st_size > self.policy.max_file_bytes:
            raise SourceDigestError("manifest file exceeds per-file byte limit")
        return WorkspaceEntry(
            resource_id,
            WorkspaceEntryKind.FILE,
            self.digest(resource_id),
            size_bytes=stat.st_size,
            mode=stat.st_mode & 0o7777,
        )

    def manifest(
        self,
        manifest_id: str,
        resource_ids: Iterable[str],
        *,
        root_label: str = "",
    ) -> WorkspaceManifest:
        seen = set()
        entries = []
        total_bytes = 0
        for resource_id in resource_ids:
            if resource_id in seen:
                continue
            seen.add(resource_id)
            if len(entries) >= self.policy.max_manifest_entries:
                raise SourceDigestError("source manifest entry limit exceeded")
            item = self.entry(resource_id)
            total_bytes += item.size_bytes
            if total_bytes > self.policy.max_manifest_bytes:
                raise SourceDigestError("source manifest byte limit exceeded")
            entries.append(item)
        return WorkspaceManifest(
            manifest_id,
            tuple(entries),
            root_label=root_label,
        )
