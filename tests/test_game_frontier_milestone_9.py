from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive, ArchiveError
import pytest


def _export(cid: str = "c1"):
    ledger = CampaignLedger(campaign_id=cid)
    session = FrontierSession(session_id="s1")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest="a" * 64, mesh_vertex_count=20, mesh_triangle_count=8,
            reconstruction_digest="b" * 64, adapter_id="m9",
        ),
        percepts=("x",), goal="hold",
    )
    ledger.add(session)
    return export_campaign(ledger, audit_receipt(ledger))


def test_store_and_get():
    archive = CampaignArchive()
    export = _export()
    manifest = archive.store(export)
    assert archive.get(manifest).campaign_id == "c1"
    assert len(archive) == 1


def test_rejects_duplicate():
    archive = CampaignArchive()
    export = _export()
    archive.store(export)
    with pytest.raises(ArchiveError):
        archive.store(export)


def test_missing():
    with pytest.raises(ArchiveError):
        CampaignArchive().get("a" * 64)


def test_list_sorted():
    archive = CampaignArchive()
    archive.store(_export("a"))
    archive.store(_export("b"))
    manifests = archive.list_manifests()
    assert list(manifests) == sorted(manifests)
    assert len(manifests) == 2
