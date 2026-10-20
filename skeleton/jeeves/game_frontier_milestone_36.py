"""Milestone 36: same_head.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def same(a, b):
    return a.head == b.head
