"""Milestone 23: longest.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def longest(receipts):
    return max(receipts, key=lambda r: r.length)
