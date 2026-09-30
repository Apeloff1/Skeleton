from __future__ import annotations
import pytest
from scripts.build_p1_adversarial_ac01_evidence import AXIS_ID,EXPECTED_MODES,REGRESSIONS,ROOT,AC01EvidenceError,build_ac01_evidence
TEST_HEAD="a"*40

def test_ac01_covers_exact_required_modes():
    r=build_ac01_evidence(ROOT,expected_head=TEST_HEAD)
    assert r["axis_id"]==AXIS_ID=="AC-01"
    assert r["candidate_count"]==1
    assert tuple(r["candidate"]["required_evidence_modes"])==EXPECTED_MODES
    assert {x["category"] for x in r["candidate"]["evidence"]}==set(EXPECTED_MODES)

def test_ac01_proofs_bind_exact_head_and_real_regressions():
    c=build_ac01_evidence(ROOT,expected_head=TEST_HEAD)["candidate"]
    for mode in EXPECTED_MODES:
        p=c["proofs"][mode]
        assert p["expected_head"]==TEST_HEAD
        assert p["regression"]["path"]==REGRESSIONS[mode][0]
        assert p["regression"]["required_tokens"]==[REGRESSIONS[mode][1]]
        assert len(p["proof_digest"])==64

def test_ac01_is_non_authoritative():
    r=build_ac01_evidence(ROOT,expected_head=TEST_HEAD)
    assert r["non_authoritative"] is True
    assert r["creates_bindings"] is False
    assert r["accepts_risk"] is False
    assert r["candidate"]["recommended_severity"]=="high"
    assert r["candidate"]["recommended_disposition"]=="evidence"

@pytest.mark.parametrize("head",["","a"*39,"A"*40,"g"*40,"a"*41])
def test_ac01_rejects_invalid_exact_head(head):
    with pytest.raises(AC01EvidenceError,match="expected_head must be lowercase 40-character git SHA"):
        build_ac01_evidence(ROOT,expected_head=head)
