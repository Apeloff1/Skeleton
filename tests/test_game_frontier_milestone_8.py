from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
import pytest
from skeleton.jeeves.game_frontier_campaign import CampaignError


def _ledger() -> CampaignLedger:
    ledger = CampaignLedger(campaign_id="export-1")
    session = FrontierSession(session_id="s1")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest="a" * 64, mesh_vertex_count=20, mesh_triangle_count=8,
            reconstruction_digest="b" * 64, adapter_id="m8",
        ),
        percepts=("x",), goal="hold",
    )
    ledger.add(session)
    return ledger


def test_export_stable():
    ledger = _ledger()
    audit = audit_receipt(ledger)
    a = export_campaign(ledger, audit)
    b = export_campaign(ledger, audit)
    assert a.manifest == b.manifest
    assert a.session_count == 1


def test_export_rejects_bad_audit():
    ledger = _ledger()
    with pytest.raises(CampaignError):
        export_campaign(ledger, "short")
    with pytest.raises(CampaignError):
        export_campaign(ledger, "0" * 64)
    with pytest.raises(CampaignError):
        export_campaign(ledger, None)
