"""Milestone 41: scale.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def scale(r, k):
    return r.length * k
