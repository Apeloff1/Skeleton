"""Milestone 43: over.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def over(r, limit):
    return r.length > limit
