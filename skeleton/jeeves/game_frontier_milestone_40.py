"""Milestone 40: is_singleton.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def singleton(r):
    return r.length == 1
