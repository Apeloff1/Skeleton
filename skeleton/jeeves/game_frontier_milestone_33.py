"""Milestone 33: pair.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def pair(a, b):
    return (a.receipt, b.receipt)
