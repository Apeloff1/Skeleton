from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac12_evidence import (
    ANCHORS,
    AXIS_ID,
    EXPECTED_MODES,
    OWNER_ID,
    ROOT,
    TOKENS,
    AC12EvidenceError,
    build_ac12_evidence,
)

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_ac12_evidence(ROOT, expected_head=TEST_HEAD)


def test_ac12_candidate_covers_exact_required_modes() -> None:
    report = _report()
    candidate = report["candidate"]

    assert report["axis_id"] == AXIS_ID == "AC-12"
    assert report["candidate_count"] == 1
    assert report["already_bound_count"] == 0
    assert report["candidate_binding_count"] == 1
    assert report["required_evidence_mode_count"] == 4
    assert candidate["binding_present"] is False
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(EXPECTED_MODES)


def test_ac12_proofs_pin_real_filesystem_and_network_controls() -> None:
    candidate = _report()["candidate"]

    for mode in EXPECTED_MODES:
        proof = candidate["proofs"][mode]
        assert proof["axis_id"] == AXIS_ID
        assert proof["mode"] == mode
        assert proof["expected_head"] == TEST_HEAD
        assert [row["path"] for row in proof["anchors"]] == list(ANCHORS[mode])
        assert all(len(row["sha256"]) == 64 for row in proof["anchors"])
        assert tuple(proof["required_tokens"]) == TOKENS[mode]
        assert len(proof["proof_digest"]) == 64


def test_ac12_mode_contracts_cover_required_adversarial_boundaries() -> None:
    assert "test_normalization_rejects_escape_or_ambiguous_paths" in TOKENS[
        "canonicalization_fuzz"
    ]
    assert "test_read_remains_bound_when_parent_path_is_swapped" in TOKENS[
        "toctou_race"
    ]
    assert "test_stream_write_cannot_escape_after_parent_path_swap" in TOKENS[
        "toctou_race"
    ]
    assert "validate_connected_peer" in TOKENS["resource_binding"]
    assert "test_mixed_dns_answer_with_any_private_address_fails_closed" in TOKENS[
        "path_network_adversarial"
    ]
    assert "test_redirect_cannot_change_security_boundary_by_default" in TOKENS[
        "path_network_adversarial"
    ]


def test_ac12_candidate_preserves_authority_boundaries() -> None:
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


def test_ac12_evidence_refs_bind_exact_head_and_mode_proofs() -> None:
    candidate = _report()["candidate"]
    by_category = {row["category"]: row for row in candidate["evidence"]}

    for mode in EXPECTED_MODES:
        proof = candidate["proofs"][mode]
        ref = by_category[mode]
        assert ref["digest"] == proof["proof_digest"]
        assert ref["source"] == (
            f"p1:adversarial-ac12-evidence:{AXIS_ID}:{mode}:{TEST_HEAD}"
        )


def test_ac12_candidate_matches_live_obligation_shape() -> None:
    candidate = _report()["candidate"]

    assert candidate["obligation_id"].startswith("P1-ADVERSARIAL-AC-12-")
    assert len(candidate["obligation_digest"]) == 64
    assert candidate["statement"]
    assert len(candidate["candidate_digest"]) == 64


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_ac12_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        AC12EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_ac12_evidence(ROOT, expected_head=head)
