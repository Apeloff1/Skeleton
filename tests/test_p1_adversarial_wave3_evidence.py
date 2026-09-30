from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_wave3_evidence import (
    AXIS_IDS,
    AXIS_PROOFS,
    EXPECTED_AXIS_COUNT,
    ROOT,
    Wave3EvidenceError,
    build_wave3_evidence,
)

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_wave3_evidence(ROOT, expected_head=TEST_HEAD)


def test_wave3_has_exact_nine_axis_scope() -> None:
    assert EXPECTED_AXIS_COUNT == 9
    assert AXIS_IDS == (
        "AC-02",
        "AC-03",
        "AC-04",
        "AC-05",
        "AC-06",
        "AC-07",
        "AC-09",
        "AC-18",
        "AC-24",
    )
    assert tuple(AXIS_PROOFS) == AXIS_IDS


def test_wave3_candidates_match_live_required_modes() -> None:
    report = _report()
    assert report["axis_count"] == EXPECTED_AXIS_COUNT
    assert report["already_bound_count"] == 0
    assert report["candidate_binding_count"] == EXPECTED_AXIS_COUNT

    by_axis = {row["axis_id"]: row for row in report["candidates"]}
    assert set(by_axis) == set(AXIS_IDS)

    for axis_id, mode_proofs in AXIS_PROOFS.items():
        candidate = by_axis[axis_id]
        assert candidate["binding_present"] is False
        assert tuple(candidate["required_evidence_modes"]) == tuple(mode_proofs)
        assert {item["category"] for item in candidate["evidence"]} == set(mode_proofs)
        assert candidate["obligation_id"].startswith(f"P1-ADVERSARIAL-{axis_id}-")
        assert len(candidate["obligation_digest"]) == 64
        assert len(candidate["candidate_digest"]) == 64


def test_wave3_all_proofs_pin_tracked_real_controls() -> None:
    report = _report()
    for candidate in report["candidates"]:
        for mode in candidate["required_evidence_modes"]:
            proof = candidate["proofs"][mode]
            assert proof["axis_id"] == candidate["axis_id"]
            assert proof["mode"] == mode
            assert proof["expected_head"] == TEST_HEAD
            assert proof["required_tokens"]
            assert proof["anchors"]
            assert all(len(anchor["sha256"]) == 64 for anchor in proof["anchors"])
            assert all(anchor["required_tokens"] for anchor in proof["anchors"])
            assert len(proof["proof_digest"]) == 64


def test_wave3_preserves_governance_authority_boundaries() -> None:
    report = _report()
    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["lowers_severity"] is False
    assert report["promotes_maturity"] is False

    for candidate in report["candidates"]:
        assert candidate["owner_id"] == "ACC-P1-EVID-04"
        assert candidate["recommended_severity"] == "high"
        assert candidate["recommended_disposition"] == "evidence"
        assert candidate["non_authoritative"] is True
        assert candidate["creates_binding"] is False
        assert candidate["accepts_risk"] is False
        assert candidate["lowers_severity"] is False
        assert candidate["promotes_maturity"] is False


def test_wave3_evidence_refs_bind_exact_head_and_proof_digest() -> None:
    report = _report()
    for candidate in report["candidates"]:
        by_category = {item["category"]: item for item in candidate["evidence"]}
        for mode, proof in candidate["proofs"].items():
            evidence = by_category[mode]
            assert evidence["digest"] == proof["proof_digest"]
            assert evidence["source"] == (
                f"p1:adversarial-wave3:{candidate['axis_id']}:{mode}:{TEST_HEAD}"
            )


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_wave3_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        Wave3EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_wave3_evidence(ROOT, expected_head=head)
