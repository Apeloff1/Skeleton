"""Milestone 62: odd_length.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def odd(r):
    return r.length % 2 == 1
