"""Milestone 56: lengths.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def lengths(receipts):
    return tuple(r.length for r in receipts)
