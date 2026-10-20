"""Milestone 31: first.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def first(receipts):
    if not receipts: raise ValueError('empty')
    return receipts[0]
