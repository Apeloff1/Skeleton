"""Milestone 42: bounded.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def bounded(r, limit):
    return r.length <= limit
