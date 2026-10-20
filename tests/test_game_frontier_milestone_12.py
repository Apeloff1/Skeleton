from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_12 import SnapshotHistory


def _export(tag: str):
    ledger = CampaignLedger(campaign_id="c")
    session = FrontierSession(session_id="s")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest=tag * 64, mesh_vertex_count=20, mesh_triangle_count=8,
            reconstruction_digest="b" * 64, adapter_id="m12",
        ),
        percepts=("x",), goal="hold",
    )
    ledger.add(session)
    return export_campaign(ledger, audit_receipt(ledger))


def test_history_records_and_verifies():
    archive = CampaignArchive()
    history = SnapshotHistory()
    history.record(archive)
    archive.store(_export("a"))
    history.record(archive)
    assert len(history) == 2
    assert history.verify()
    assert len(history.head) == 64


def test_empty_does_not_verify():
    assert SnapshotHistory().verify() is False


def test_history_is_deterministic():
    archive = CampaignArchive()
    archive.store(_export("a"))
    a = SnapshotHistory()
    b = SnapshotHistory()
    a.record(archive)
    b.record(archive)
    assert a.head == b.head


def test_tamper_detected():
    archive = CampaignArchive()
    history = SnapshotHistory()
    history.record(archive)
    archive.store(_export("a"))
    history.record(archive)
    history.entries[0] = history.entries[1]
    assert history.verify() is False
