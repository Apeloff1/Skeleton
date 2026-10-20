"""Milestone 59: min_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def min_length(receipts):
    return min(r.length for r in receipts)
