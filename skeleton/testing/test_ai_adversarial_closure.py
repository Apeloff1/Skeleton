from __future__ import annotations

import json

from scripts import check_ai_adversarial_closure as checker


def test_adversarial_closure_is_complete() -> None:
    assert checker.validate() == []
    data = json.loads(checker.CLOSURE.read_text(encoding="utf-8"))
    assert len(data["closure_axes"]) == 24
    assert len(data["compound_campaigns"]) == 12
    assert set(data["work_package_coverage"]) == set(checker.EXPECTED_WPS)


def test_every_work_package_has_deep_cross_condition_coverage() -> None:
    data = json.loads(checker.CLOSURE.read_text(encoding="utf-8"))
    minimum = data["minimum_axis_count_per_work_package"]
    assert minimum >= 6
    for wp, refs in data["work_package_coverage"].items():
        assert len(refs) >= minimum, wp
        assert set(refs).issubset(checker.EXPECTED_AXES)


def test_compound_campaigns_combine_multiple_failure_axes() -> None:
    data = json.loads(checker.CLOSURE.read_text(encoding="utf-8"))
    for campaign in data["compound_campaigns"]:
        assert len(campaign["axes"]) >= 3, campaign["id"]
        assert campaign["oracle"].strip(), campaign["id"]


def test_evidence_bundle_binds_fault_manifest_and_artifact() -> None:
    data = json.loads(checker.CLOSURE.read_text(encoding="utf-8"))
    fields = set(data["evidence_bundle_required_fields"])
    assert {
        "git_sha", "artifact_digest", "config_digest", "environment_digest",
        "fault_manifest_digest", "raw_evidence_refs", "verifier_identity", "signoff_ref",
    }.issubset(fields)


def test_breadth_freeze_is_preserved() -> None:
    data = json.loads(checker.CLOSURE.read_text(encoding="utf-8"))
    assert data["scope"]["adds_top_level_volumes"] is False
