"""Milestone 11: archive snapshots and diff.

Captures a content-addressed snapshot of an archive and diffs
two snapshots. Candidate-only. In-memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .game_frontier_milestone_9 import CampaignArchive

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MANIFESTS = 4096


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveSnapshot:
    """Immutable view of an archive at one moment."""

    manifests: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        _verified_snapshot(self)


def _verified_snapshot(value: ArchiveSnapshot) -> ArchiveSnapshot:
    """Check the bounded canonical content, rather than trusting its label."""
    if not isinstance(value, ArchiveSnapshot):
        raise SnapshotError("archive snapshot type required")
    manifests = value.manifests
    if type(manifests) is not tuple or len(manifests) > _MAX_MANIFESTS:
        raise SnapshotError("snapshot manifests must be a bounded tuple")
    if any(type(item) is not str or _DIGEST.fullmatch(item) is None for item in manifests):
        raise SnapshotError("snapshot manifest identity invalid")
    if manifests != tuple(sorted(set(manifests))):
        raise SnapshotError("snapshot manifests must be sorted and unique")
    if type(value.digest) is not str or _DIGEST.fullmatch(value.digest) is None:
        raise SnapshotError("snapshot digest invalid")
    payload = json.dumps(list(manifests), separators=(",", ":"))
    if sha256(payload.encode()).hexdigest() != value.digest:
        raise SnapshotError("snapshot digest does not bind its manifests")
    return value


def snapshot(archive: CampaignArchive) -> ArchiveSnapshot:
    """Content-address the current manifest set."""
    manifests = archive.list_manifests()
    payload = json.dumps(list(manifests), separators=(",", ":"))
    return ArchiveSnapshot(manifests=manifests, digest=sha256(payload.encode()).hexdigest())


def diff(before: ArchiveSnapshot, after: ArchiveSnapshot) -> dict:
    """Report added and removed manifests between two snapshots."""
    _verified_snapshot(before)
    _verified_snapshot(after)
    before_set = set(before.manifests)
    after_set = set(after.manifests)
    return {
        "added": tuple(sorted(after_set - before_set)),
        "removed": tuple(sorted(before_set - after_set)),
        "unchanged": len(before_set & after_set),
        "same": before.digest == after.digest,
    }
