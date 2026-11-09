"""Keep legacy verified wave-4 signoffs distinct from unverified security gapfill."""
from __future__ import annotations

from copy import deepcopy

from scripts.check_ai_build_accountability import (
    _historical_wave4_verification_pending_independent_scope as scope,
)


def _fixtures():
    volume = {
        "key": "VOL-166",
        "implementation_status": "implemented",
        "completion_checkbox": False,
        "completion_checkbox_mark": "[ ]",
        "gaps": ["independent replay pending"],
    }
    record = {
        "id": "ACC-VOL-166", "status": "verified",
        "checkbox": True, "checkbox_mark": "[x]",
        "implementation_signoff": {"signed": True, "signer_id": "builder"},
        "verification_signoff": {
            "signed": True, "signer_id": "independent",
            "statement": "Verification-signed after wave-4 admit/reject passed",
        },
        "completed_at_utc": "2026-10-09T14:28:00Z",
        "evidence": ["git-head:historical-signed-evidence"],
        "history": [{"to_status": "verified"}],
    }
    candidate = {
        "schema_version": "skeleton.ai.security_governance_gapfill_candidate.v1",
        "status": "implementation_candidate",
        "volume_refs": [
            "VOL-166", "VOL-167", "VOL-169", "VOL-172", "VOL-173",
            "VOL-174", "VOL-175", "VOL-176", "VOL-177", "VOL-178",
        ],
        "promotion_state": {
            "completion_checkbox": False, "implementation_signed": False,
            "verification_signed": False, "may_self_close": False,
            "production_authority": False,
        },
    }
    return volume, record, candidate


def test_historical_scope_is_recognized_without_granting_new_completion():
    volume, record, candidate = _fixtures()
    assert scope(volume, record, candidate)
    assert volume["completion_checkbox"] is False
    assert candidate["promotion_state"]["verification_signed"] is False


def test_historical_scope_fails_closed_if_new_candidate_is_promoted():
    volume, record, candidate = _fixtures()
    for key in candidate["promotion_state"]:
        altered = deepcopy(candidate)
        altered["promotion_state"][key] = True
        assert not scope(volume, record, altered), key


def test_historical_scope_requires_independent_signed_previous_evidence():
    volume, record, candidate = _fixtures()
    for case in ("unsigned", "same_verifier", "missing_evidence", "wrong_scope"):
        altered = deepcopy(record)
        if case == "unsigned":
            altered["verification_signoff"]["signed"] = False
        elif case == "same_verifier":
            altered["verification_signoff"]["signer_id"] = "builder"
        elif case == "missing_evidence":
            altered["evidence"] = []
        else:
            altered["verification_signoff"]["statement"] = "not the requested historical suite"
        assert not scope(volume, altered, candidate), case


def test_historical_scope_requires_masterplan_remain_unverified():
    volume, record, candidate = _fixtures()
    for key, bad in [
        ("implementation_status", "verified"), ("completion_checkbox", True),
        ("completion_checkbox_mark", "[x]"), ("gaps", []),
    ]:
        altered = deepcopy(volume)
        altered[key] = bad
        assert not scope(altered, record, candidate), key


def test_historical_scope_rejects_unlisted_volume_or_unsigned_candidate():
    volume, record, candidate = _fixtures()
    volume["key"] = "VOL-168"
    record["id"] = "ACC-VOL-168"
    assert not scope(volume, record, candidate)
    volume, record, candidate = _fixtures()
    candidate["volume_refs"].remove("VOL-166")
    assert not scope(volume, record, candidate)
