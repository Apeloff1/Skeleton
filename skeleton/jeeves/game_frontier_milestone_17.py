"""Milestone 17: receipt_verify.

Confirm a receipt length matches its history.
Candidate-only. In-memory.
"""
from __future__ import annotations

from .game_frontier_milestone_14 import HistoryReceipt, between
from .game_frontier_milestone_13 import HistoryQueryError
from .game_frontier_milestone_12 import SnapshotHistory


def matches(receipt_obj, history):
    return receipt_obj.length == len(history) and receipt_obj.head == history.head
