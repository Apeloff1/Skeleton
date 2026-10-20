"""Milestone 34: delta.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def delta(a, b):
    return b.length - a.length
