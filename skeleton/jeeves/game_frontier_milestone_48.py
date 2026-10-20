"""Milestone 48: label.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def label(r):
    return f'{r.length}:{r.head[:6]}'
