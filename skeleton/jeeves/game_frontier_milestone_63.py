"""Milestone 63: receipt_tail.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def tail(r, n):
    return r.receipt[-n:]
