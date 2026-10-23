from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_12 import SnapshotHistory
from skeleton.jeeves.game_frontier_milestone_13 import (
    HistoryBound, compact, at, latest, HistoryQueryError,
)
import pytest


def _fill(history: SnapshotHistory, n: int) -> None:
    archive = CampaignArchive()
    for i in range(n):
        history.record(archive)
        if i < n - 1:
            ledger = CampaignLedger(campaign_id="c")
            session = FrontierSession(session_id="s")
            session.step(
                clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
                evidence=WorldModelEvidence(
                    source_digest=chr(97 + i) * 64, mesh_vertex_count=20,
                    mesh_triangle_count=8, reconstruction_digest="b" * 64, adapter_id="m13",
                ),
                percepts=("x",), goal="hold",
            )
            ledger.add(session)
            archive.store(export_campaign(ledger, audit_receipt(ledger)))


def test_compact_drops_oldest():
    history = SnapshotHistory()
    _fill(history, 4)
    removed = compact(history, HistoryBound(max_entries=2))
    assert removed == 2
    assert len(history) == 2
    assert history.verify()


def test_compact_noop():
    history = SnapshotHistory()
    _fill(history, 2)
    assert compact(history, HistoryBound(max_entries=5)) == 0


def test_at_and_latest():
    history = SnapshotHistory()
    _fill(history, 3)
    assert at(history, 0).digest != latest(history).digest
    assert at(history, 2).digest == latest(history).digest


def test_empty_raises():
    with pytest.raises(HistoryQueryError):
        latest(SnapshotHistory())


def test_bound_rejects_zero():
    with pytest.raises(HistoryQueryError):
        HistoryBound(max_entries=0)



def test_corrupt_head_never_becomes_new_authoritative_chain():
    history = SnapshotHistory()
    _fill(history, 4)
    history.head = "0" * 64
    original_entries = list(history.entries)
    with pytest.raises(HistoryQueryError, match="verify"):
        compact(history, HistoryBound(max_entries=2))
    assert history.entries == original_entries
    assert history.head == "0" * 64


def test_reject_tampered_snapshots_even_for_read_only_queries():
    history = SnapshotHistory()
    _fill(history, 3)
    history.entries.reverse()
    with pytest.raises(HistoryQueryError, match="verify"):
        at(history, 0)
    with pytest.raises(HistoryQueryError, match="verify"):
        latest(history)


def test_invalid_index_type_denied_without_coercion():
    history = SnapshotHistory()
    _fill(history, 2)
    for value in (True, 1.0, "1", -1):
        with pytest.raises(HistoryQueryError):
            at(history, value)


def test_noop_compaction_still_refuses_corrupted_history():
    history = SnapshotHistory()
    _fill(history, 2)
    history.head = "0" * 64
    with pytest.raises(HistoryQueryError, match="verify"):
        compact(history, HistoryBound(max_entries=5))
