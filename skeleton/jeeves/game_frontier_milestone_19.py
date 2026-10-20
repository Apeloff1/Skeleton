"""Milestone 19: receipt_age.

Count snapshots after a receipt was taken.
Candidate-only. In-memory.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt, between
from .game_frontier_milestone_13 import HistoryQueryError
from .game_frontier_milestone_12 import SnapshotHistory


def age(receipt_obj, history):
    if not history.verify():
        raise HistoryQueryError('history must verify')
    return len(history) - receipt_obj.length
