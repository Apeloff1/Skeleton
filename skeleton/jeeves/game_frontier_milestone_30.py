"""Milestone 30: sorted_by_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def ordered(receipts):
    return tuple(sorted(receipts, key=lambda r: r.length))
