"""Milestone 16: receipt_chain.

Chain two receipts into a parent link.
Candidate-only. In-memory.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt, between
from .game_frontier_milestone_13 import HistoryQueryError
from .game_frontier_milestone_12 import SnapshotHistory


def link(parent, child):
    if parent.receipt == child.receipt:
        raise HistoryQueryError('cannot link a receipt to itself')
    return {'parent': parent.receipt, 'child': child.receipt}
