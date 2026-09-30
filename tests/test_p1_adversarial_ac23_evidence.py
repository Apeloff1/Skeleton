from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac23_evidence import (
    AXIS_ID,
    EXPECTED_MODES,
    ROOT,
    AC23EvidenceError,
    build_ac23_evidence,
)

TEST_HEAD = "d" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_ac23_evidence(ROOT, expected_head=TEST_HEAD)


def test_ac23_candidate_covers_exact_required_modes() -> None:
    report = _report()
    candidate = report["candidate"]
    assert report["axis_id"] == AXIS_ID == "AC-23"
    assert report["candidate_count"] == 1
    assert report["already_bound_count"] + report["candidate_binding_count"] == 1
    assert report["already_bound_count"] == int(candidate["binding_present"])
    assert report["candidate_binding_count"] == int(not candidate["binding_present"])
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(EXPECTED_MODES)


def test_ac23_proofs_pin_real_aging_controls() -> None:
    candidate = _report()["candidate"]
    for mode in EXPECTED_MODES:
        proof = candidate["proofs"][mode]
        assert proof["axis_id"] == AXIS_ID
        assert proof["mode"] == mode
        assert proof["expected_head"] == TEST_HEAD
        assert proof["anchors"]
        assert all(len(row["sha256"]) == 64 for row in proof["anchors"])
        assert len(proof["proof_digest"]) == 64


def test_ac23_preserves_authority_boundary() -> None:
    report = _report()
    candidate = report["candidate"]
    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["lowers_severity"] is False
    assert report["promotes_maturity"] is False
    assert candidate["recommended_severity"] == "high"
    assert candidate["recommended_disposition"] == "evidence"
    assert candidate["creates_binding"] is False
    assert candidate["accepts_risk"] is False
    assert candidate["lowers_severity"] is False
    assert candidate["promotes_maturity"] is False


def test_ac23_evidence_refs_bind_exact_head() -> None:
    candidate = _report()["candidate"]
    for row in candidate["evidence"]:
        assert row["source"].endswith(":" + TEST_HEAD)
        assert len(row["digest"]) == 64


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_ac23_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        AC23EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_ac23_evidence(ROOT, expected_head=head)
