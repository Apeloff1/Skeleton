"""Milestone 15: fork_detect.

Detect whether two receipts share a common head.
Candidate-only. In-memory.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt, between
from .game_frontier_milestone_13 import HistoryQueryError
from .game_frontier_milestone_12 import SnapshotHistory


def same_lineage(a, b):
    if len(a.head)!=64 or len(b.head)!=64:
        raise HistoryQueryError('receipts must carry SHA-256 heads')
    return a.head == b.head
