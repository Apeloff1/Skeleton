from __future__ import annotations

from functools import lru_cache

import pytest

from scripts.build_p1_adversarial_ac22_evidence import (
    AXIS_ID,
    EXPECTED_MODES,
    OWNER_ID,
    ROOT,
    AC22EvidenceError,
    build_ac22_evidence,
    build_environment_manifest,
)

TEST_HEAD = "a" * 40


@lru_cache(maxsize=1)
def _manifest_digest() -> str:
    return build_environment_manifest(ROOT)["manifest_digest"]


@lru_cache(maxsize=1)
def _report() -> dict:
    digest = _manifest_digest()
    return build_ac22_evidence(
        ROOT,
        expected_head=TEST_HEAD,
        x64_manifest_digest=digest,
        x64_replay_digest=digest,
        arm64_manifest_digest=digest,
        arm64_replay_digest=digest,
        x64_arch="x86_64",
        arm64_arch="aarch64",
    )


def test_ac22_candidate_covers_exact_required_modes() -> None:
    report = _report()
    candidate = report["candidate"]

    assert report["axis_id"] == AXIS_ID == "AC-22"
    assert report["candidate_count"] == 1
    assert report["required_evidence_mode_count"] == 4
    assert tuple(candidate["required_evidence_modes"]) == EXPECTED_MODES
    assert {row["category"] for row in candidate["evidence"]} == set(EXPECTED_MODES)


def test_ac22_manifest_is_tracked_and_lock_bound() -> None:
    manifest = _report()["candidate"]["environment_manifest"]

    assert len(manifest["manifest_digest"]) == 64
    assert len(manifest["anchors"]) >= 10
    assert [row["path"] for row in manifest["lock_anchors"]] == [
        "pyproject.toml",
        "backend/pyproject.toml",
        "backend/requirements.txt",
        "frontend/package.json",
        "frontend/yarn.lock",
    ]
    assert all(len(row["sha256"]) == 64 for row in manifest["anchors"])


def test_ac22_replay_and_cross_environment_digests_match() -> None:
    proofs = _report()["candidate"]["proofs"]
    replay = proofs["environment_replay"]
    cross = proofs["cross_environment_reproduction"]

    assert replay["replay_stable"] is True
    assert len({
        replay["x64_manifest_digest"],
        replay["x64_replay_digest"],
        replay["arm64_manifest_digest"],
        replay["arm64_replay_digest"],
    }) == 1
    assert cross["x64_arch"] == "x86_64"
    assert cross["arm64_arch"] == "aarch64"
    assert cross["cross_environment_digest_match"] is True


def test_ac22_candidate_preserves_authority_boundaries() -> None:
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


def test_ac22_evidence_refs_bind_exact_head_and_proofs() -> None:
    candidate = _report()["candidate"]
    for ref in candidate["evidence"]:
        mode = ref["category"]
        proof = candidate["proofs"][mode]
        assert ref["digest"] == proof["proof_digest"]
        assert ref["source"] == (
            f"p1:adversarial-ac22-evidence:{AXIS_ID}:{mode}:{TEST_HEAD}"
        )


def test_ac22_rejects_cross_environment_digest_drift() -> None:
    digest = _manifest_digest()
    wrong = "0" * 64 if digest != "0" * 64 else "1" * 64
    with pytest.raises(
        AC22EvidenceError,
        match="arm64_manifest_digest does not match canonical manifest digest",
    ):
        build_ac22_evidence(
            ROOT,
            expected_head=TEST_HEAD,
            x64_manifest_digest=digest,
            x64_replay_digest=digest,
            arm64_manifest_digest=wrong,
            arm64_replay_digest=digest,
            x64_arch="x86_64",
            arm64_arch="aarch64",
        )


@pytest.mark.parametrize(
    ("x64_arch", "arm64_arch"),
    [("amd64", "aarch64"), ("x86_64", "arm64"), ("aarch64", "x86_64")],
)
def test_ac22_rejects_architecture_contract_drift(
    x64_arch: str,
    arm64_arch: str,
) -> None:
    digest = _manifest_digest()
    with pytest.raises(AC22EvidenceError, match="expected architectures"):
        build_ac22_evidence(
            ROOT,
            expected_head=TEST_HEAD,
            x64_manifest_digest=digest,
            x64_replay_digest=digest,
            arm64_manifest_digest=digest,
            arm64_replay_digest=digest,
            x64_arch=x64_arch,
            arm64_arch=arm64_arch,
        )


@pytest.mark.parametrize("head", ["", "a" * 39, "A" * 40, "g" * 40, "a" * 41])
def test_ac22_rejects_invalid_exact_head(head: str) -> None:
    digest = _manifest_digest()
    with pytest.raises(
        AC22EvidenceError,
        match="expected_head must be lowercase 40-character git SHA",
    ):
        build_ac22_evidence(
            ROOT,
            expected_head=head,
            x64_manifest_digest=digest,
            x64_replay_digest=digest,
            arm64_manifest_digest=digest,
            arm64_replay_digest=digest,
            x64_arch="x86_64",
            arm64_arch="aarch64",
        )
