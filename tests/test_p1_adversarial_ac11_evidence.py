from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac11_evidence import (
    AXIS_ID,
    EXPECTED_MODES,
    OWNER_ID,
    ROOT,
    AC11EvidenceError,
    build_ac11_evidence,
)

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _report() -> dict:
    return build_ac11_evidence(ROOT, expected_head=TEST_HEAD)


def test_ac11_candidate_covers_exact_required_modes() -> None:
    report = _report()
    candidate = report["candidate"]

    assert report["axis_id"] == AXIS_ID == "AC-11"
    assert report["candidate_count"] == 1
    assert report["required_evidence_mode_count"] == 4
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(EXPECTED_MODES)


def test_ac11_candidate_preserves_authority_boundaries() -> None:
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


def test_ac11_semantic_drift_is_detected_without_version_change() -> None:
    candidate = _report()["candidate"]
    proof = candidate["proofs"]["drift_eval"]["mutation"]

    assert proof["field"] == "breadth_freeze.p1_application_policy"
    assert proof["before"] == "forbid"
    assert proof["after"] == "allow"
    assert proof["expected_error"] in proof["observed_errors"]


def test_ac11_evidence_digest_invalidates_on_semantic_change() -> None:
    candidate = _report()["candidate"]
    proof = candidate["proofs"]["evidence_invalidation"]

    assert proof["schema_version_before"] == proof["schema_version_after"]
    assert proof["digest_changed"] is True
    assert proof["baseline_digest"] != proof["mutated_digest"]
    assert len(proof["baseline_digest"]) == 64
    assert len(proof["mutated_digest"]) == 64


def test_ac11_live_canaries_and_contract_probes_pass() -> None:
    candidate = _report()["candidate"]

    for mode in ("semantic_canary", "contract_probe"):
        proof = candidate["proofs"][mode]
        assert proof["validators"]
        assert all(row["returncode"] == 0 for row in proof["validators"])
        assert all(len(row["stdout_digest"]) == 64 for row in proof["validators"])
        assert all(len(row["stderr_digest"]) == 64 for row in proof["validators"])


def test_ac11_evidence_refs_bind_each_proof_and_exact_head() -> None:
    candidate = _report()["candidate"]

    for ref in candidate["evidence"]:
        mode = ref["category"]
        proof = candidate["proofs"][mode]
        assert ref["digest"] == proof["proof_digest"]
        assert ref["source"] == (
            f"p1:adversarial-ac11-evidence:{AXIS_ID}:{mode}:{TEST_HEAD}"
        )


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_ac11_rejects_invalid_exact_head(head: str) -> None:
    with pytest.raises(
        AC11EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_ac11_evidence(ROOT, expected_head=head)
