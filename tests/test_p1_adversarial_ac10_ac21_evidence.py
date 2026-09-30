from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac10_ac21_evidence import (
    AXES,
    PROOFS,
    ROOT,
    EvidenceError,
    build_evidence,
)

TEST_HEAD = "e" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_evidence(ROOT, expected_head=TEST_HEAD)


def test_exact_axis_and_mode_scope() -> None:
    report = _report()
    assert tuple(report["axis_ids"]) == AXES == ("AC-10", "AC-21")
    assert report["axis_count"] == 2
    assert report["already_bound_count"] == 0
    assert report["candidate_binding_count"] == 2
    by_axis = {row["axis_id"]: row for row in report["candidates"]}
    assert set(by_axis) == set(AXES)
    for axis_id in AXES:
        candidate = by_axis[axis_id]
        assert tuple(candidate["required_evidence_modes"]) == tuple(PROOFS[axis_id])
        assert {row["category"] for row in candidate["evidence"]} == set(PROOFS[axis_id])


def test_proofs_pin_tracked_real_controls() -> None:
    for candidate in _report()["candidates"]:
        for mode, proof in candidate["proofs"].items():
            assert proof["axis_id"] == candidate["axis_id"]
            assert proof["mode"] == mode
            assert proof["expected_head"] == TEST_HEAD
            assert proof["anchors"]
            assert all(len(row["sha256"]) == 64 for row in proof["anchors"])
            assert len(proof["proof_digest"]) == 64


def test_authority_boundary_is_evidence_only() -> None:
    report = _report()
    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["lowers_severity"] is False
    assert report["promotes_maturity"] is False
    for candidate in report["candidates"]:
        assert candidate["binding_present"] is False
        assert candidate["recommended_severity"] == "high"
        assert candidate["recommended_disposition"] == "evidence"
        assert candidate["creates_binding"] is False
        assert candidate["accepts_risk"] is False
        assert candidate["lowers_severity"] is False
        assert candidate["promotes_maturity"] is False


def test_evidence_refs_bind_exact_head() -> None:
    for candidate in _report()["candidates"]:
        for evidence in candidate["evidence"]:
            assert evidence["source"].endswith(":" + TEST_HEAD)
            assert len(evidence["digest"]) == 64


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_invalid_exact_head_is_rejected(head: str) -> None:
    with pytest.raises(
        EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_evidence(ROOT, expected_head=head)
