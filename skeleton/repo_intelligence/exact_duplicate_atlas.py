"""Lossless, read-only exact-duplicate atlas over a verified GitIndex snapshot.

A content-match is a review candidate, NEVER evidence that a path can be
removed: imports, runtime roles, license, alias and binary provenance matter.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

from .git_index import GitIndexSnapshot


@dataclass(frozen=True, slots=True)
class ExactDuplicateCluster:
    blob: str
    mode: str
    size: int
    paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "blob": self.blob,
            "mode": self.mode,
            "size": self.size,
            "paths": list(self.paths),
            "automatic_deletion_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class ExactDuplicateAtlas:
    head: str
    source_digest: str
    object_format: str
    tracked_files: int
    tracked_bytes: int
    duplicate_file_paths: int
    clusters: tuple[ExactDuplicateCluster, ...]
    all_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "skeleton.repository.atlas.exact.v1",
            "head": self.head,
            "source_digest": self.source_digest,
            "object_format": self.object_format,
            "tracked_files": self.tracked_files,
            "tracked_bytes": self.tracked_bytes,
            "enumerated_paths": len(self.all_paths),
            "all_paths": list(self.all_paths),
            "duplicate_file_paths": self.duplicate_file_paths,
            "clusters": [cluster.to_dict() for cluster in self.clusters],
            "automatic_deletion_allowed": False,
            "coverage_complete": True,
        }


def build_exact_duplicate_atlas(snapshot: GitIndexSnapshot) -> ExactDuplicateAtlas:
    """Index every tracked path, or fail rather than emit partial evidence."""
    if not isinstance(snapshot, GitIndexSnapshot):
        raise TypeError("snapshot must be a verified GitIndexSnapshot")
    expected_hex = 40 if snapshot.object_format == "sha1" else 64 if snapshot.object_format == "sha256" else 0
    if (not expected_hex or not isinstance(snapshot.head, str)
            or re.fullmatch(r"[0-9a-f]+", snapshot.head) is None
            or len(snapshot.head) != expected_hex):
        raise ValueError("a pinned Git HEAD with supported object format is required")
    if snapshot.tracked_files != len(snapshot.files):
        raise ValueError("snapshot path coverage count disagrees with file inventory")

    paths = set()
    groups: dict[tuple[str, str, int], list[str]] = defaultdict(list)
    counted_bytes = 0
    for entry in snapshot.files:
        if (not entry.path or entry.path in paths or entry.deleted
                or entry.working_tree or entry.working_mode is not None):
            raise ValueError("duplicate, modified or missing tracked file prevents pinned atlas")
        if (not isinstance(entry.size, int) or isinstance(entry.size, bool)
                or entry.size < 0):
            raise ValueError("invalid tracked-file size")
        if (not isinstance(entry.effective_blob, str)
                or re.fullmatch(r"[0-9a-f]+", entry.effective_blob) is None
                or len(entry.effective_blob) != expected_hex
                or entry.effective_blob != entry.index_blob):
            raise ValueError("unverified Git blob identity")
        paths.add(entry.path)
        counted_bytes += entry.size
        # Preserve mode distinctions and gitlink/symlink provenance.
        groups[(entry.effective_blob, entry.mode, entry.size)].append(entry.path)

    if counted_bytes != snapshot.tracked_bytes:
        raise ValueError("snapshot byte coverage mismatch")

    duplicates = tuple(
        ExactDuplicateCluster(blob, mode, size, tuple(sorted(members)))
        for (blob, mode, size), members in sorted(groups.items())
        if len(members) > 1
    )
    return ExactDuplicateAtlas(
        head=snapshot.head,
        source_digest=snapshot.source_digest,
        object_format=snapshot.object_format,
        tracked_files=snapshot.tracked_files,
        tracked_bytes=snapshot.tracked_bytes,
        duplicate_file_paths=sum(len(item.paths) for item in duplicates),
        clusters=duplicates,
        all_paths=tuple(sorted(paths)),
    )
