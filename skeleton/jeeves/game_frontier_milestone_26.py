"""Milestone 26: has_head.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def has(receipts, head):
    return any(r.head == head for r in receipts)
