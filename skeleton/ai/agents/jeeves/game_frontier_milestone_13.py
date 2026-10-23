"""Milestone 13: history query and compaction.

Queries a snapshot history and compacts it to a bound.
Candidate-only. In-memory.
"""
from __future__ import annotations

from dataclasses import dataclass

from .game_frontier_milestone_12 import SnapshotHistory
from .game_frontier_milestone_11 import ArchiveSnapshot


class HistoryQueryError(ValueError):
    pass


@dataclass(frozen=True)
class HistoryBound:
    """Maximum number of snapshots a history may retain."""

    max_entries: int

    def __post_init__(self) -> None:
        if type(self.max_entries) is not int or not 1 <= self.max_entries <= 1024:
            raise HistoryQueryError("max_entries must be 1..1024")


def compact(history: SnapshotHistory, bound: HistoryBound) -> int:
    """Drop oldest snapshots until the history fits the bound.

    Returns the number removed. The head is recomputed.
    """
    if not history.verify():
        raise HistoryQueryError("history must verify before compaction")
    overflow = len(history) - bound.max_entries
    if overflow <= 0:
        return 0
    history.entries = history.entries[overflow:]
    # recompute head over the retained entries
    from hashlib import sha256
    import json
    head = ""
    for index, snap in enumerate(history.entries):
        payload = json.dumps(
            {"prev": head, "digest": snap.digest, "index": index},
            sort_keys=True,
            separators=(",", ":"),
        )
        head = sha256(payload.encode()).hexdigest()
    history.head = head
    return overflow


def at(history: SnapshotHistory, index: int) -> ArchiveSnapshot:
    """Return the snapshot at a zero-based index."""
    if not history.verify():
        raise HistoryQueryError("history must verify before lookup")
    if type(index) is not int or not 0 <= index < len(history.entries):
        raise HistoryQueryError("index out of range")
    return history.entries[index]


def latest(history: SnapshotHistory) -> ArchiveSnapshot:
    """Return the most recent snapshot."""
    if not history.verify():
        raise HistoryQueryError("history must verify before lookup")
    return history.entries[-1]
