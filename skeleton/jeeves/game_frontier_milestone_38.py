"""Milestone 38: head_prefix.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def prefix(r, n):
    return r.head[:n]
