"""Milestone 29: receipt_ids.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def ids(receipts):
    return tuple(r.receipt for r in receipts)
