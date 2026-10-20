"""Milestone 54: skip.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def skip(receipts, n):
    return tuple(receipts[n:])
