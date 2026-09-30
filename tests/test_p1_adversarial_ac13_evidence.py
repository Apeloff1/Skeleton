from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac13_evidence import (
    AXIS_ID,
    EXPECTED_MODES,
    IMPLEMENTATION,
    MODE_TEST_TOKENS,
    OWNER_ID,
    REGRESSIONS,
    ROOT,
    AC13EvidenceError,
    build_ac13_evidence,
)

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_ac13_evidence(ROOT, expected_head=TEST_HEAD)


def test_ac13_candidate_covers_exact_required_modes() -> None:
    report = _report()
    candidate = report["candidate"]

    assert report["axis_id"] == AXIS_ID == "AC-13"
    assert report["candidate_count"] == 1
    assert report["required_evidence_mode_count"] == 4
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(EXPECTED_MODES)


def test_ac13_proofs_pin_real_archive_sandbox_controls() -> None:
    candidate = _report()["candidate"]

    for mode in EXPECTED_MODES:
        proof = candidate["proofs"][mode]
        assert proof["axis_id"] == AXIS_ID
        assert proof["mode"] == mode
        assert proof["expected_head"] == TEST_HEAD
        assert proof["implementation"]["path"] == IMPLEMENTATION
        assert proof["regression"]["path"] == REGRESSIONS
        assert len(proof["implementation"]["sha256"]) == 64
        assert len(proof["regression"]["sha256"]) == 64
        assert tuple(proof["regression"]["required_tokens"]) == MODE_TEST_TOKENS[mode]
        assert len(proof["proof_digest"]) == 64


def test_ac13_mode_contracts_cover_bombs_and_complexity_bounds() -> None:
    assert "test_zip_compression_ratio_bound_is_enforced" in MODE_TEST_TOKENS[
        "decompression_bomb"
    ]
    assert "test_archive_expansion_ratio_bound_is_enforced" in MODE_TEST_TOKENS[
        "decompression_bomb"
    ]
    assert "max_stream_chunks_per_member" in MODE_TEST_TOKENS[
        "complexity_budget"
    ]
    assert "test_member_count_bound_is_enforced" in MODE_TEST_TOKENS[
        "parser_limits"
    ]
    assert "test_zip_rejects_traversal_absolute_or_ambiguous_paths" in MODE_TEST_TOKENS[
        "fuzz"
    ]


def test_ac13_candidate_preserves_authority_boundaries() -> None:
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


def test_ac13_evidence_refs_bind_exact_head_and_mode_proofs() -> None:
    candidate = _report()["candidate"]
    by_category = {row["category"]: row for row in candidate["evidence"]}

    for mode in EXPECTED_MODES:
        proof = candidate["proofs"][mode]
        ref = by_category[mode]
        assert ref["digest"] == proof["proof_digest"]
        assert ref["source"] == (
            f"p1:adversarial-ac13-evidence:{AXIS_ID}:{mode}:{TEST_HEAD}"
        )


def test_ac13_candidate_matches_live_obligation_shape() -> None:
    candidate = _report()["candidate"]

    assert candidate["obligation_id"].startswith("P1-ADVERSARIAL-AC-13-")
    assert len(candidate["obligation_digest"]) == 64
    assert candidate["statement"]
    assert len(candidate["candidate_digest"]) == 64


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_ac13_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        AC13EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_ac13_evidence(ROOT, expected_head=head)
