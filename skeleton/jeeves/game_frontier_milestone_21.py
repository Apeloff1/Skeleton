"""Milestone 21: count_receipts.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def count(receipts):
    return len(receipts)
