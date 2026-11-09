"""Regression for milestone 6 campaign ledger."""
from __future__ import annotations

import pytest

from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import (
    CampaignLedger, compare_campaigns, audit_receipt, CampaignError,
)


def _session(sid: str, tag: str = "a") -> FrontierSession:
    session = FrontierSession(session_id=sid)
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest=tag * 64, mesh_vertex_count=40, mesh_triangle_count=16,
            reconstruction_digest="b" * 64, adapter_id="camp-v1",
        ),
        percepts=("ridge",), goal="summit",
    )
    return session


def test_ledger_records_and_verifies():
    ledger = CampaignLedger(campaign_id="camp-1")
    ledger.add(_session("s1"))
    ledger.add(_session("s2", "d"))
    assert ledger.verify()
    assert len(ledger.sessions) == 2
    assert len(ledger.head) == 64


def test_ledger_rejects_unverified_session():
    ledger = CampaignLedger(campaign_id="camp-2")
    empty = FrontierSession(session_id="empty")
    with pytest.raises(CampaignError):
        ledger.add(empty)


def test_compare_flags_divergence():
    left = CampaignLedger(campaign_id="L")
    right = CampaignLedger(campaign_id="R")
    left.add(_session("s1"))
    right.add(_session("s1", "e"))
    result = compare_campaigns(left, right)
    assert result["session_count_match"] is True
    assert result["head_match"] is False


def test_compare_matches_identical():
    left = CampaignLedger(campaign_id="L")
    right = CampaignLedger(campaign_id="R")
    left.add(_session("s1"))
    right.add(_session("s1"))
    result = compare_campaigns(left, right)
    assert result["head_match"] is True


def test_audit_receipt_stable():
    ledger = CampaignLedger(campaign_id="audit")
    ledger.add(_session("s1"))
    a = audit_receipt(ledger)
    b = audit_receipt(ledger)
    assert a == b
    assert len(a) == 64


def test_audit_rejects_empty():
    with pytest.raises(CampaignError):
        audit_receipt(CampaignLedger(campaign_id="empty"))


def test_ledger_rejects_bad_id():
    with pytest.raises(CampaignError):
        CampaignLedger(campaign_id="")
