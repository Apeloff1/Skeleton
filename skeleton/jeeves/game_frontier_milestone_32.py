"""Milestone 32: last.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def last(receipts):
    if not receipts: raise ValueError('empty')
    return receipts[-1]
