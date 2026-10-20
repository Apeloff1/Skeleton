"""Milestone 20: head_advance.

Confirm the head moved forward.
Candidate-only. In-memory.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt, between
from .game_frontier_milestone_13 import HistoryQueryError
from .game_frontier_milestone_12 import SnapshotHistory


def advanced(before, after):
    return before.head != after.head and after.length >= before.length
