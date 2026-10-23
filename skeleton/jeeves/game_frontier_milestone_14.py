"""Milestone 14: history receipt and range query.

Content-addresses a verified snapshot history and returns a
slice of snapshots. Candidate-only. In-memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .game_frontier_milestone_12 import SnapshotHistory
from .game_frontier_milestone_11 import ArchiveSnapshot
from .game_frontier_milestone_13 import HistoryQueryError


@dataclass(frozen=True)
class HistoryReceipt:
    """Content-addressed receipt for a verified history."""

    length: int
    head: str
    receipt: str


def receipt(history: SnapshotHistory) -> HistoryReceipt:
    """Emit a receipt. Fails closed if the history does not verify."""
    if not history.verify():
        raise HistoryQueryError("history must verify before receipt")
    payload = json.dumps(
        {"head": history.head, "length": len(history), "digests": [s.digest for s in history.entries]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return HistoryReceipt(
        length=len(history),
        head=history.head,
        receipt=sha256(payload.encode()).hexdigest(),
    )


def between(history: SnapshotHistory, start: int, end: int) -> tuple[ArchiveSnapshot, ...]:
    """Return snapshots in the half-open range [start, end)."""
    if not history.verify():
        raise HistoryQueryError("history must verify before range query")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(history.entries):
        raise HistoryQueryError("range out of bounds")
    return tuple(history.entries[start:end])
