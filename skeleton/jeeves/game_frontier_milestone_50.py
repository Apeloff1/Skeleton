"""Milestone 50: contains.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def contains(receipts, receipt):
    return any(r.receipt == receipt for r in receipts)
