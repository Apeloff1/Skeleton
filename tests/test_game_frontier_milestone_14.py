from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_12 import SnapshotHistory
from skeleton.jeeves.game_frontier_milestone_14 import receipt, between
from skeleton.jeeves.game_frontier_milestone_13 import HistoryQueryError
import pytest


def _history(n: int) -> SnapshotHistory:
    archive = CampaignArchive()
    history = SnapshotHistory()
    for _ in range(n):
        history.record(archive)
    return history


def test_receipt_stable():
    history = _history(3)
    a = receipt(history)
    b = receipt(history)
    assert a.receipt == b.receipt
    assert a.length == 3
    assert len(a.receipt) == 64


def test_receipt_rejects_empty():
    with pytest.raises(HistoryQueryError):
        receipt(SnapshotHistory())


def test_between_slice():
    history = _history(4)
    window = between(history, 1, 3)
    assert len(window) == 2
    assert window[0].digest == history.entries[1].digest


def test_between_rejects_bad_range():
    with pytest.raises(HistoryQueryError):
        between(_history(2), 1, 1)
