from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_wave4_evidence import (
    AXES,
    BATCH_ID,
    MODES,
    OWNER_ID,
    PROOFS,
    ROOT,
    Wave4EvidenceError,
    build_axis_evidence,
)

TEST_HEAD = "e" * 40


@lru_cache(maxsize=None)
def _report(axis_id: str) -> dict:
    return build_axis_evidence(
        ROOT,
        axis_id=axis_id,
        expected_head=TEST_HEAD,
    )


@pytest.mark.parametrize("axis_id", AXES)
def test_wave4_candidate_covers_exact_required_modes(axis_id: str) -> None:
    report = _report(axis_id)
    candidate = report["candidate"]
    assert report["axis_id"] == axis_id
    assert report["engine"] == "p1-adversarial-wave4-evidence-v1"
    assert report["batch_id"] == BATCH_ID
    assert report["candidate_count"] == 1
    assert report["already_bound_count"] == 0
    assert report["candidate_binding_count"] == 1
    assert report["required_evidence_mode_count"] == 4
    assert candidate["binding_present"] is False
    assert tuple(candidate["required_evidence_modes"]) == MODES[axis_id]
    assert {row["category"] for row in candidate["evidence"]} == set(
        MODES[axis_id]
    )


@pytest.mark.parametrize("axis_id", AXES)
def test_wave4_proofs_pin_tracked_runtime_controls(axis_id: str) -> None:
    candidate = _report(axis_id)["candidate"]
    for mode in MODES[axis_id]:
        proof = candidate["proofs"][mode]
        expected_paths = [
            path
            for path, _tokens in PROOFS[axis_id][mode]
        ]
        expected_tokens = [
            token
            for _path, tokens in PROOFS[axis_id][mode]
            for token in tokens
        ]
        assert proof["axis_id"] == axis_id
        assert proof["mode"] == mode
        assert proof["expected_head"] == TEST_HEAD
        assert [row["path"] for row in proof["anchors"]] == expected_paths
        assert proof["required_tokens"] == expected_tokens
        assert all(len(row["sha256"]) == 64 for row in proof["anchors"])
        assert len(proof["proof_digest"]) == 64


@pytest.mark.parametrize("axis_id", AXES)
def test_wave4_preserves_authority_boundaries(axis_id: str) -> None:
    report = _report(axis_id)
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


@pytest.mark.parametrize("axis_id", AXES)
def test_wave4_evidence_refs_bind_exact_head(axis_id: str) -> None:
    candidate = _report(axis_id)["candidate"]
    by_category = {
        row["category"]: row
        for row in candidate["evidence"]
    }
    for mode in MODES[axis_id]:
        proof = candidate["proofs"][mode]
        ref = by_category[mode]
        assert ref["digest"] == proof["proof_digest"]
        assert ref["source"] == (
            f"p1:adversarial-wave4-evidence:{axis_id}:"
            f"{mode}:{TEST_HEAD}"
        )


@pytest.mark.parametrize("axis_id", AXES)
def test_wave4_candidate_matches_live_obligation(axis_id: str) -> None:
    candidate = _report(axis_id)["candidate"]
    assert candidate["obligation_id"].startswith(
        f"P1-ADVERSARIAL-{axis_id}-"
    )
    assert len(candidate["obligation_digest"]) == 64
    assert candidate["statement"]
    assert len(candidate["candidate_digest"]) == 64


@pytest.mark.parametrize(
    "head",
    ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41],
)
def test_wave4_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        Wave4EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_axis_evidence(
            ROOT,
            axis_id="AC-01",
            expected_head=head,
        )


def test_wave4_rejects_unknown_axis() -> None:
    with pytest.raises(
        Wave4EvidenceError,
        match="unsupported wave-4 axis",
    ):
        build_axis_evidence(
            ROOT,
            axis_id="AC-99",
            expected_head=TEST_HEAD,
        )
