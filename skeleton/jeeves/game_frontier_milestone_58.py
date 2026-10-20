"""Milestone 58: max_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def max_length(receipts):
    return max(r.length for r in receipts)
