"""Milestone 49: index_of.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def index_of(receipts, receipt):
    for i, r in enumerate(receipts):
        if r.receipt == receipt: return i
    return -1
