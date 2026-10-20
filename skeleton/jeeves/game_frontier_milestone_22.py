"""Milestone 22: unique_heads.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def unique(receipts):
    return len({r.head for r in receipts})
