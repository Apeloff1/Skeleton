"""Milestone 64: head_tail.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def tail(r, n):
    return r.head[-n:]
