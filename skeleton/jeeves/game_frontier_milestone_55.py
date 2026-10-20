"""Milestone 55: reverse.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def reverse(receipts):
    return tuple(reversed(receipts))
