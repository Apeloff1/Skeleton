"""Milestone 45: head_eq.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def eq(a, b):
    return a.head == b.head
