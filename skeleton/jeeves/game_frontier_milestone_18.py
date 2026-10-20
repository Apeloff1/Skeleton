"""Milestone 18: window_digest.

Digest a between-window of snapshots.
Candidate-only. In-memory.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt, between
from .game_frontier_milestone_13 import HistoryQueryError
from .game_frontier_milestone_12 import SnapshotHistory


def window_digest(history, start, end):
    from hashlib import sha256
    snaps = between(history, start, end)
    payload = '|'.join(s.digest for s in snaps)
    return sha256(payload.encode()).hexdigest()
