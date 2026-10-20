"""Milestone 46: length_eq.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def eq(a, b):
    return a.length == b.length
