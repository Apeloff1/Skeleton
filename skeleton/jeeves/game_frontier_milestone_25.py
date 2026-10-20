"""Milestone 25: total_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def total(receipts):
    return sum(r.length for r in receipts)
