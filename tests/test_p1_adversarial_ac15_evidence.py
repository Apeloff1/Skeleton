from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac15_evidence import (
    AXIS_ID,
    EXPECTED_MODES,
    OWNER_ID,
    PROOF_ANCHORS,
    ROOT,
    AC15EvidenceError,
    build_ac15_evidence,
)

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_ac15_evidence(ROOT, expected_head=TEST_HEAD)


def test_ac15_candidate_covers_exact_required_modes() -> None:
    report = _report()
    candidate = report["candidate"]

    assert report["axis_id"] == AXIS_ID == "AC-15"
    assert report["candidate_count"] == 1
    assert report["required_evidence_mode_count"] == 4
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(
        EXPECTED_MODES
    )


def test_ac15_candidate_preserves_authority_boundaries() -> None:
    report = _report()
    candidate = report["candidate"]

    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["accepts_risk"] is False
    assert report["lowers_severity"] is False
    assert report["promotes_maturity"] is False

    assert candidate["owner_id"] == OWNER_ID
    assert candidate["recommended_severity"] == "high"
    assert candidate["recommended_disposition"] == "evidence"
    assert candidate["creates_binding"] is False
    assert candidate["accepts_risk"] is False
    assert candidate["lowers_severity"] is False
    assert candidate["promotes_maturity"] is False


def test_ac15_mode_proofs_are_tracked_and_digest_bound() -> None:
    candidate = _report()["candidate"]

    assert set(candidate["proof_modes"]) == set(EXPECTED_MODES)
    for mode in EXPECTED_MODES:
        proof = candidate["proof_modes"][mode]
        assert proof["axis_id"] == AXIS_ID
        assert proof["mode"] == mode
        assert proof["expected_head"] == TEST_HEAD
        assert len(proof["proof_digest"]) == 64
        assert [row["path"] for row in proof["anchors"]] == list(
            PROOF_ANCHORS[mode]
        )
        assert all(len(row["sha256"]) == 64 for row in proof["anchors"])
        ref = next(
            row for row in candidate["evidence"] if row["category"] == mode
        )
        assert ref["digest"] == proof["proof_digest"]
        assert ref["source"] == (
            f"p1:adversarial-ac15-evidence:{AXIS_ID}:{mode}:{TEST_HEAD}"
        )


def test_ac15_candidate_is_bound_to_live_obligation_digest() -> None:
    candidate = _report()["candidate"]

    assert candidate["obligation_id"].startswith("P1-ADVERSARIAL-AC-15-")
    assert len(candidate["obligation_digest"]) == 64
    assert candidate["statement"]
    assert len(candidate["candidate_digest"]) == 64


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_ac15_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        AC15EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_ac15_evidence(ROOT, expected_head=head)
