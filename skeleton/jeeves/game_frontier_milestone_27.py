"""Milestone 27: filter_min.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def filter_min(receipts, n):
    return tuple(r for r in receipts if r.length >= n)
