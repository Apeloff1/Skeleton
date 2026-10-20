"""Milestone 61: even_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def even(r):
    return r.length % 2 == 0
