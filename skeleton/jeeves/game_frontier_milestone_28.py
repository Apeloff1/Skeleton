"""Milestone 28: filter_max.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def filter_max(receipts, n):
    return tuple(r for r in receipts if r.length <= n)
