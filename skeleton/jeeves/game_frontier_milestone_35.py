"""Milestone 35: same_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def same(a, b):
    return a.length == b.length
