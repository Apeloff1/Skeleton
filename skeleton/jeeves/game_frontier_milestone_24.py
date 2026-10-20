"""Milestone 24: shortest.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def shortest(receipts):
    return min(receipts, key=lambda r: r.length)
