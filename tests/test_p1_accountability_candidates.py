from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_p1_accountability_candidates.py"
ACCOUNTABILITY = ROOT / "machine/ai_build_accountability.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_p1_accountability_candidates",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_report_is_non_authoritative_and_complete() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    assert report["primary_volume_count"] == 107
    assert report["authoritative"] is False
    assert report["may_apply"] is False
    assert report["signatures_created"] == 0
    assert len(report["packets"]) == 107
    assert len(report["report_digest"]) == 64

    keys = [packet["volume_key"] for packet in report["packets"]]
    assert keys == sorted(keys)
    assert len(set(keys)) == 107


def test_candidate_state_distribution_preserves_existing_signed_cases() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    assert report["review_state_counts"] == {
        "already_target_floor_eligible": 3,
        "implementation_review_ready": 104,
    }
    eligible = {
        packet["volume_key"]
        for packet in report["packets"]
        if packet["review_state"] == "already_target_floor_eligible"
    }
    assert eligible == {"VOL-013", "VOL-014", "VOL-253"}


def test_unsigned_candidates_require_governed_signoff_without_applying_it() -> None:
    module = _module()
    report = module.build_candidates(ROOT)

    for packet in report["packets"]:
        assert packet["authoritative"] is False
        assert packet["may_apply"] is False
        assert len(packet["packet_digest"]) == 64
        assert packet["signing_required"] is True
        assert packet["mapped_task_ids"]
        assert packet["implementation_paths"]
        assert packet["tests"]
        assert packet["evaluations"]
        assert packet["evidence_refs"]
        assert all(
            not reference.startswith("planned:")
            for field in (
                "implementation_paths",
                "tests",
                "evaluations",
                "evidence_refs",
            )
            for reference in packet[field]
        )

        if packet["review_state"] == "implementation_review_ready":
            assert packet["implementation_signed"] is False
            assert "implementation_signoff_required" in packet[
                "governance_blockers"
            ]
            assert "independent_verification_signoff_required" in packet[
                "governance_blockers"
            ]
        else:
            assert packet["review_state"] == "already_target_floor_eligible"
            assert packet["implementation_signed"] is True
            assert packet["verification_signed"] is True


def test_candidate_generation_does_not_mutate_accountability_ledger() -> None:
    module = _module()
    before = ACCOUNTABILITY.read_bytes()

    report = module.build_candidates(ROOT)

    assert report["source_digests"]["accountability"]
    assert ACCOUNTABILITY.read_bytes() == before


def test_candidate_packets_are_deterministic() -> None:
    module = _module()

    first = module.build_candidates(ROOT)
    second = module.build_candidates(ROOT)

    assert first == second


def test_candidate_report_can_be_written_as_review_artifact(tmp_path: Path) -> None:
    module = _module()
    report = module.build_candidates(ROOT)
    destination = tmp_path / "review-candidates.json"

    destination.write_text(
        module._canonical_text(report),
        encoding="utf-8",
    )
    loaded = json.loads(destination.read_text(encoding="utf-8"))

    assert loaded == report
    assert loaded["authoritative"] is False
    assert loaded["signatures_created"] == 0
