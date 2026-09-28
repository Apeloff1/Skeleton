from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.reproducibility import (
    ReplayDisposition,
    ReproducibilityBundle,
    ReproducibilityEvaluation,
)
from skeleton.release.evidence import (
    build_evidence,
    evidence_digest,
    evaluate_release_ready,
)
from skeleton.release.qualification import (
    ReleaseLifecycleMode,
    ReleaseLifecycleReceipt,
    ReleaseQualificationError,
    qualify_release_candidate,
)


COMMIT = "a" * 40
INSTALLER_DIGEST = "2" * 64
CONFIG_DIGEST = "3" * 64
ENVIRONMENT_DIGEST = "4" * 64


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _release_evidence():
    artifact = b"deterministic-release-artifact"
    sbom = b'{"bomFormat":"CycloneDX","specVersion":"1.6"}\n'
    build_input = b"build==1.0\n"
    test_log = b"tests passed\n"
    eval_log = b"eval passed\n"
    return build_evidence(
        source_commit=COMMIT,
        source_date_epoch=1_800_000_000,
        build_inputs=(
            {
                "name": "requirements-build.txt",
                "sha256": _sha(build_input),
                "size": len(build_input),
            },
        ),
        artifacts=(
            {
                "artifact_id": "release",
                "name": "skeleton-release.zip",
                "sha256": _sha(artifact),
                "size": len(artifact),
                "locator": {
                    "kind": "release-store",
                    "uri": "artifact://release/skeleton-release.zip",
                },
                "upload": {
                    "status": "complete",
                    "bytes_transferred": len(artifact),
                    "sha256": _sha(artifact),
                },
            },
        ),
        sbom={
            "name": "release-sbom.cdx.json",
            "sha256": _sha(sbom),
            "size": len(sbom),
            "locator": {
                "kind": "release-store",
                "uri": "artifact://release/release-sbom.cdx.json",
            },
        },
        provenance={
            "schema_version": 1,
            "digest": _sha(b"provenance-v1"),
            "source_commit": COMMIT,
        },
        asset_provenance=(),
        test_evidence=(
            {
                "evidence_id": "tests",
                "name": "tests.xml",
                "sha256": _sha(test_log),
                "result": "pass",
            },
        ),
        eval_evidence=(
            {
                "evidence_id": "eval",
                "name": "eval.xml",
                "sha256": _sha(eval_log),
                "result": "pass",
            },
        ),
    )


def _release_gate(evidence=None, **overrides: object):
    evidence = _release_evidence() if evidence is None else evidence
    gate = evaluate_release_ready(
        evidence,
        expected_commit=COMMIT,
    )
    values: dict[str, object] = {
        "release_ready": gate.release_ready,
        "reasons": gate.reasons,
        "evidence_digest": gate.evidence_digest,
    }
    values.update(overrides)
    return type(gate)(**values)


def _repro(
    release_digest: str,
    **overrides: object,
) -> ReproducibilityBundle:
    values: dict[str, object] = {
        "repository": "Apeloff1/Skeleton",
        "commit_sha": COMMIT,
        "task_id": "P1-REL-01",
        "accountability_id": "ACC-P1-REL-01",
        "configuration_digest": CONFIG_DIGEST,
        "environment_digest": ENVIRONMENT_DIGEST,
        "verifier_id": "verifier:release-replay",
        "verifier_digest": "5" * 64,
        "test_manifest_digest": "6" * 64,
        "runner_id": "runner-release",
        "runner_digest": "7" * 64,
        "budget_id": "budget-release",
        "budget_digest": "8" * 64,
        "source_date_epoch": 1_800_000_000,
        "expected_subject_digest": "9" * 64,
        "expected_evidence_digest": release_digest,
        "inputs": (
            EvidenceRef(
                source="release://candidate",
                digest=release_digest,
                category="release_evidence",
            ),
        ),
    }
    values.update(overrides)
    return ReproducibilityBundle(**values)


def _replay(
    bundle: ReproducibilityBundle,
    **overrides: object,
) -> ReproducibilityEvaluation:
    values: dict[str, object] = {
        "bundle_digest": bundle.bundle_digest,
        "disposition": ReplayDisposition.REPRODUCED,
        "compatible": True,
        "reproduced": True,
        "incompatibilities": (),
        "replay_subject_digest": bundle.expected_subject_digest,
        "replay_evidence_digest": bundle.expected_evidence_digest,
        "failure_digest": None,
    }
    values.update(overrides)
    return ReproducibilityEvaluation(**values)


def _deps() -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            source="p1:prod-05:tenant-storage:tenant/a:read",
            digest="a" * 64,
            category="tenant_storage_boundary",
        ),
        EvidenceRef(
            source="p1:learn-03:candidate:candidate-digest",
            digest="b" * 64,
            category="candidate_qualification",
        ),
        EvidenceRef(
            source="p1:auto-06:safe-autonomy-bundle",
            digest="c" * 64,
            category="safe_autonomy_qualification",
        ),
    )


def _receipt(
    mode: ReleaseLifecycleMode,
    release_digest: str,
    **overrides: object,
) -> ReleaseLifecycleReceipt:
    values: dict[str, object] = {
        "mode": mode,
        "source_commit": COMMIT,
        "release_evidence_digest": release_digest,
        "installer_metadata_digest": INSTALLER_DIGEST,
        "configuration_digest": CONFIG_DIGEST,
        "environment_digest": ENVIRONMENT_DIGEST,
        "verifier_id": f"verifier:{mode.value}",
        "verifier_digest": "e" * 64,
        "test_manifest_digest": "f" * 64,
        "evidence_refs": (
            EvidenceRef(
                source=f"lifecycle://{mode.value}",
                digest="0" * 64,
                category=mode.value,
            ),
        ),
        "passed": True,
        "independent": True,
        "production_mutation_count": 0,
    }
    values.update(overrides)
    return ReleaseLifecycleReceipt(**values)


def _receipts(
    release_digest: str,
) -> tuple[ReleaseLifecycleReceipt, ...]:
    return tuple(
        _receipt(mode, release_digest)
        for mode in ReleaseLifecycleMode
    )


def _qualify(**overrides: object):
    release_evidence = overrides.pop(
        "release_evidence",
        _release_evidence(),
    )
    release_digest = evidence_digest(release_evidence)
    release_gate = overrides.pop(
        "release_gate",
        _release_gate(release_evidence),
    )
    reproducibility = overrides.pop(
        "reproducibility",
        _repro(release_digest),
    )
    replay = overrides.pop(
        "reproducibility_evaluation",
        _replay(reproducibility),
    )
    values: dict[str, object] = {
        "source_commit": COMMIT,
        "release_evidence": release_evidence,
        "release_gate": release_gate,
        "reproducibility": reproducibility,
        "reproducibility_evaluation": replay,
        "dependency_evidence": _deps(),
        "lifecycle_receipts": _receipts(release_digest),
        "installer_metadata_digest": INSTALLER_DIGEST,
        "configuration_digest": CONFIG_DIGEST,
    }
    values.update(overrides)
    return qualify_release_candidate(**values)


def test_complete_release_bundle_qualifies() -> None:
    decision = _qualify()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.source_commit == COMMIT
    assert len(decision.lifecycle_receipt_digests) == 3
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "release_qualification"
    assert evidence.digest == decision.decision_digest


def test_release_evidence_gate_must_be_ready() -> None:
    evidence = _release_evidence()
    gate = _release_gate(
        evidence,
        release_ready=False,
        reasons=("missing SBOM",),
    )
    decision = _qualify(
        release_evidence=evidence,
        release_gate=gate,
    )

    assert decision.accepted is False
    assert "release-evidence-not-ready" in decision.reasons


def test_release_gate_digest_must_match_release_document() -> None:
    evidence = _release_evidence()
    gate = _release_gate(
        evidence,
        evidence_digest="f" * 64,
    )
    decision = _qualify(
        release_evidence=evidence,
        release_gate=gate,
    )

    assert decision.accepted is False
    assert "release-evidence-digest-mismatch" in decision.reasons


def test_reproducibility_must_bind_exact_commit_and_release_digest() -> None:
    evidence = _release_evidence()
    digest = evidence_digest(evidence)
    bad_commit = _repro(digest, commit_sha="b" * 40)
    decision = _qualify(
        release_evidence=evidence,
        reproducibility=bad_commit,
        reproducibility_evaluation=_replay(bad_commit),
    )
    assert decision.accepted is False
    assert "reproducibility-commit-mismatch" in decision.reasons

    bad_input = EvidenceRef(
        source="release://candidate",
        digest="f" * 64,
        category="release_evidence",
    )
    bad_bundle = _repro(digest, inputs=(bad_input,))
    decision = _qualify(
        release_evidence=evidence,
        reproducibility=bad_bundle,
        reproducibility_evaluation=_replay(bad_bundle),
    )
    assert decision.accepted is False
    assert (
        "reproducibility-release-evidence-mismatch"
        in decision.reasons
    )


def test_reproducibility_evaluation_must_be_exact_and_reproduced() -> None:
    evidence = _release_evidence()
    digest = evidence_digest(evidence)
    bundle = _repro(digest)
    replay = _replay(
        bundle,
        disposition=ReplayDisposition.FAILED,
        reproduced=False,
        incompatibilities=("replay execution failed",),
        failure_digest="d" * 64,
        replay_subject_digest=None,
        replay_evidence_digest=None,
    )
    decision = _qualify(
        release_evidence=evidence,
        reproducibility=bundle,
        reproducibility_evaluation=replay,
    )

    assert decision.accepted is False
    assert "reproducibility-replay-not-reproduced" in decision.reasons
    assert "reproducibility-replay-failed" in decision.reasons


def test_reproducibility_release_input_must_be_exactly_one() -> None:
    evidence = _release_evidence()
    digest = evidence_digest(evidence)
    unrelated = EvidenceRef(
        source="other://evidence",
        digest="a" * 64,
        category="other",
    )
    bundle = _repro(digest, inputs=(unrelated,))
    decision = _qualify(
        release_evidence=evidence,
        reproducibility=bundle,
        reproducibility_evaluation=_replay(bundle),
    )
    assert decision.accepted is False
    assert (
        "reproducibility-release-evidence-cardinality"
        in decision.reasons
    )


@pytest.mark.parametrize(
    "category",
    (
        "tenant_storage_boundary",
        "candidate_qualification",
        "safe_autonomy_qualification",
    ),
)
def test_required_dependency_evidence_cannot_be_missing(
    category: str,
) -> None:
    deps = tuple(item for item in _deps() if item.category != category)
    decision = _qualify(dependency_evidence=deps)

    assert decision.accepted is False
    assert (
        f"dependency-evidence-cardinality:{category}"
        in decision.reasons
    )


def test_dependency_source_substitution_blocks() -> None:
    deps = list(_deps())
    deps[0] = EvidenceRef(
        source="wrong://tenant-storage",
        digest=deps[0].digest,
        category=deps[0].category,
    )
    decision = _qualify(dependency_evidence=tuple(deps))

    assert decision.accepted is False
    assert (
        "dependency-evidence-source-mismatch:tenant_storage_boundary"
        in decision.reasons
    )


@pytest.mark.parametrize("mode", tuple(ReleaseLifecycleMode))
def test_each_lifecycle_mode_is_required_exactly_once(
    mode: ReleaseLifecycleMode,
) -> None:
    evidence = _release_evidence()
    digest = evidence_digest(evidence)
    receipts = tuple(
        item for item in _receipts(digest) if item.mode is not mode
    )
    decision = _qualify(
        release_evidence=evidence,
        lifecycle_receipts=receipts,
    )

    assert decision.accepted is False
    assert (
        f"lifecycle-receipt-cardinality:{mode.value}"
        in decision.reasons
    )

    duplicate = (*_receipts(digest), _receipt(mode, digest))
    decision = _qualify(
        release_evidence=evidence,
        lifecycle_receipts=duplicate,
    )
    assert decision.accepted is False
    assert (
        f"lifecycle-receipt-cardinality:{mode.value}"
        in decision.reasons
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        (
            "source_commit",
            "b" * 40,
            "lifecycle-commit-mismatch:clean_machine",
        ),
        (
            "release_evidence_digest",
            "f" * 64,
            "lifecycle-release-digest-mismatch:clean_machine",
        ),
        (
            "installer_metadata_digest",
            "f" * 64,
            "lifecycle-installer-digest-mismatch:clean_machine",
        ),
        (
            "configuration_digest",
            "f" * 64,
            "lifecycle-config-digest-mismatch:clean_machine",
        ),
    ),
)
def test_lifecycle_identity_drift_blocks(
    field: str,
    value: str,
    reason: str,
) -> None:
    evidence = _release_evidence()
    digest = evidence_digest(evidence)
    receipts = list(_receipts(digest))
    receipts[0] = replace(receipts[0], **{field: value})
    decision = _qualify(
        release_evidence=evidence,
        lifecycle_receipts=tuple(receipts),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_lifecycle_receipt_must_be_passing_independent_and_nonmutating() -> None:
    digest = evidence_digest(_release_evidence())
    base = _receipt(ReleaseLifecycleMode.CLEAN_MACHINE, digest)

    with pytest.raises(
        ReleaseQualificationError,
        match="must be passing",
    ):
        replace(base, passed=False)
    with pytest.raises(
        ReleaseQualificationError,
        match="independently verified",
    ):
        replace(base, independent=False)
    with pytest.raises(
        ReleaseQualificationError,
        match="cannot mutate production",
    ):
        replace(base, production_mutation_count=1)


def test_lifecycle_receipt_requires_exact_mode_evidence() -> None:
    digest = evidence_digest(_release_evidence())
    with pytest.raises(
        ReleaseQualificationError,
        match="exact mode category",
    ):
        _receipt(
            ReleaseLifecycleMode.ROLLBACK,
            digest,
            evidence_refs=(
                EvidenceRef(
                    source="lifecycle://wrong",
                    digest="0" * 64,
                    category="clean_machine",
                ),
            ),
        )


def test_rejected_release_cannot_materialize_promotion_evidence() -> None:
    evidence = _release_evidence()
    gate = _release_gate(evidence, release_ready=False)
    decision = _qualify(
        release_evidence=evidence,
        release_gate=gate,
    )

    assert decision.accepted is False
    with pytest.raises(
        ReleaseQualificationError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
