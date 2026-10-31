from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_11 import snapshot, diff


def _export(tag: str):
    ledger = CampaignLedger(campaign_id="c")
    session = FrontierSession(session_id="s")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest=tag * 64, mesh_vertex_count=20, mesh_triangle_count=8,
            reconstruction_digest="b" * 64, adapter_id="m11",
        ),
        percepts=("x",), goal="hold",
    )
    ledger.add(session)
    return export_campaign(ledger, audit_receipt(ledger))


def test_snapshot_stable():
    archive = CampaignArchive()
    archive.store(_export("a"))
    a = snapshot(archive)
    b = snapshot(archive)
    assert a.digest == b.digest
    assert len(a.manifests) == 1


def test_diff_detects_add():
    archive = CampaignArchive()
    before = snapshot(archive)
    archive.store(_export("a"))
    after = snapshot(archive)
    result = diff(before, after)
    assert len(result["added"]) == 1
    assert result["removed"] == ()
    assert result["same"] is False


def test_diff_detects_remove():
    archive = CampaignArchive()
    export = _export("a")
    archive.store(export)
    before = snapshot(archive)
    del archive.entries[export.manifest]
    after = snapshot(archive)
    result = diff(before, after)
    assert len(result["removed"]) == 1
    assert result["added"] == ()


def test_diff_same():
    archive = CampaignArchive()
    archive.store(_export("a"))
    a = snapshot(archive)
    assert diff(a, a)["same"] is True
