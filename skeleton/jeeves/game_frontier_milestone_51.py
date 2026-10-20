"""Milestone 51: drop_first.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def drop(receipts):
    return tuple(receipts[1:])
