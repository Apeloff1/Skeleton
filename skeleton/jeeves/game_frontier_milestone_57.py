"""Milestone 57: heads.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def heads(receipts):
    return tuple(r.head for r in receipts)
