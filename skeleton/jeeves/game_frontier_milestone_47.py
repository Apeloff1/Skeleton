"""Milestone 47: summarize.

Candidate-only pure operation over history receipts.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt


def summarize(r):
    return {'length': r.length, 'head': r.head[:8]}
