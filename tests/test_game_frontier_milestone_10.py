from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_10 import (
    RetentionPolicy, apply_retention, query_by_campaign, RetentionError,
)
import pytest


def _export(cid: str, tag: str = "a"):
    ledger = CampaignLedger(campaign_id=cid)
    session = FrontierSession(session_id="s1")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest=tag * 64, mesh_vertex_count=20, mesh_triangle_count=8,
            reconstruction_digest="b" * 64, adapter_id="m10",
        ),
        percepts=("x",), goal="hold",
    )
    ledger.add(session)
    return export_campaign(ledger, audit_receipt(ledger))


def test_retention_drops_overflow():
    archive = CampaignArchive()
    archive.store(_export("a"))
    archive.store(_export("b"))
    archive.store(_export("c"))
    removed = apply_retention(archive, RetentionPolicy(max_entries=2))
    assert removed == 1
    assert len(archive) == 2


def test_retention_noop_when_under():
    archive = CampaignArchive()
    archive.store(_export("a"))
    assert apply_retention(archive, RetentionPolicy(max_entries=5)) == 0


def test_query_filters():
    archive = CampaignArchive()
    archive.store(_export("keep", "a"))
    archive.store(_export("drop", "d"))
    archive.store(_export("keep", "e"))
    found = query_by_campaign(archive, "keep")
    assert len(found) == 2
    assert all(e.campaign_id == "keep" for e in found)


def test_policy_rejects_zero():
    with pytest.raises(RetentionError):
        RetentionPolicy(max_entries=0)
