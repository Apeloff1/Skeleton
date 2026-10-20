"""Milestone 11: archive snapshots and diff.

Captures a content-addressed snapshot of an archive and diffs
two snapshots. Candidate-only. In-memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .game_frontier_milestone_9 import CampaignArchive


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveSnapshot:
    """Immutable view of an archive at one moment."""

    manifests: tuple[str, ...]
    digest: str


def snapshot(archive: CampaignArchive) -> ArchiveSnapshot:
    """Content-address the current manifest set."""
    manifests = archive.list_manifests()
    payload = json.dumps(list(manifests), separators=(",", ":"))
    return ArchiveSnapshot(manifests=manifests, digest=sha256(payload.encode()).hexdigest())


def diff(before: ArchiveSnapshot, after: ArchiveSnapshot) -> dict:
    """Report added and removed manifests between two snapshots."""
    if len(before.digest) != 64 or len(after.digest) != 64:
        raise SnapshotError("snapshots must carry SHA-256 digests")
    before_set = set(before.manifests)
    after_set = set(after.manifests)
    return {
        "added": tuple(sorted(after_set - before_set)),
        "removed": tuple(sorted(before_set - after_set)),
        "unchanged": len(before_set & after_set),
        "same": before.digest == after.digest,
    }
