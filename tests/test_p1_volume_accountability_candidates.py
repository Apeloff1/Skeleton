from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_p1_volume_accountability_candidates.py"
ACCOUNTABILITY = ROOT / "machine/ai_build_accountability.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_p1_volume_accountability_candidates",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_report_is_non_authoritative_and_complete() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    assert report["schema_version"] == 1
    assert report["engine"] == "p1-volume-accountability-candidates-v1"
    assert report["non_authoritative"] is True
    assert report["mutates_accountability"] is False
    assert report["creates_signatures"] is False
    assert report["requires_distinct_verifier_identity"] is True
    assert report["volume_count"] == 107
    assert len(report["records"]) == 107


def test_all_materialized_primary_volumes_are_review_ready() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    assert report["implementation_review_ready_count"] == 107
    assert report["verification_evidence_ready_count"] == 107

    for row in report["records"]:
        assert row["implementation_review_ready"] is True
        assert row["verification_evidence_ready_after_implementation"] is True
        assert row["mapped_task_ids"]
        assert row["evidence_refs"]
        assert row["implemented_non_governance_blockers"] == []
        assert row["verified_non_governance_blockers"] == []


def test_candidate_report_preserves_known_target_floor_boundary() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    eligible = {
        row["volume_key"]
        for row in report["records"]
        if row["target_floor_eligible"] is True
    }
    governed_eligible = {
        row["volume_key"]
        for row in report["records"]
        if row["implementation_signed"] is True
        and row["verification_signed"] is True
        and row["required_review_actions"] == []
    }
    assert eligible == governed_eligible
    assert report["target_floor_eligible_count"] == len(eligible)
    assert {"VOL-013", "VOL-014", "VOL-253"} <= eligible

    for row in report["records"]:
        if row["target_floor_eligible"] is True:
            continue
        assert row["required_review_actions"]
        assert (
            "implementation_signoff" in row["required_review_actions"]
            or "independent_verification_signoff"
            in row["required_review_actions"]
            or "gap_closure_or_governed_disposition"
            in row["required_review_actions"]
            or "target_floor_reconciliation"
            in row["required_review_actions"]
        )


def test_gap_blocked_summary_matches_record_actions() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    counted = sum(
        1
        for row in report["records"]
        if "gap_closure_or_governed_disposition"
        in row["required_review_actions"]
    )
    assert report["gap_blocked_count"] == counted
    assert counted > 0


def test_candidate_builder_never_mutates_accountability_ledger() -> None:
    module = _module()
    before = ACCOUNTABILITY.read_bytes()

    first = module.build_candidates(ROOT)
    second = module.build_candidates(ROOT)

    after = ACCOUNTABILITY.read_bytes()
    assert before == after
    assert first == second


def test_unsigned_candidate_actions_follow_governed_signing_order() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    for row in report["records"]:
        actions = row["required_review_actions"]
        if row["implementation_signed"] is False:
            assert "implementation_signoff" in actions
        if row["verification_signed"] is False:
            assert "independent_verification_signoff" in actions

        # The report may request review, but it never emits signer identities,
        # signature methods, signature references, or signed transitions.
        assert "signer_id" not in row
        assert "signature_method" not in row
        assert "signature_ref" not in row
        assert "signed_at_utc" not in row
