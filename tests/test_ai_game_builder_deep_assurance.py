from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    sys.modules[name] = module


def _load(name: str, relative: str) -> None:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_package("skeleton", ROOT / "skeleton")
_package("skeleton.ai", ROOT / "skeleton" / "ai")
_package("skeleton.ai.game_builder", ROOT / "skeleton" / "ai" / "game_builder")
_load("skeleton.ai.game_builder.contracts", "skeleton/ai/game_builder/contracts.py")
_load("skeleton.ai.game_builder.deep_assurance", "skeleton/ai/game_builder/deep_assurance.py")

from skeleton.ai.game_builder.contracts import (  # noqa: E402
    EvaluatorProvenance,
    canonical_digest,
)
from skeleton.ai.game_builder.deep_assurance import (  # noqa: E402
    ClosureCertificate,
    ComplexityGovernor,
    ComplexitySnapshot,
    ConstraintProofSet,
    ConstraintResult,
    DeepAssuranceError,
    EvidenceMerkleLedger,
    GranularityCoverage,
    HermeticTransformRegistry,
    IntentInvariant,
    IntentPreservationGate,
    InteractionMatrix,
    KnowledgeIngestionFirewall,
    KnowledgeSource,
    MentalModelProbe,
    PlayerMentalModelGate,
    ProjectResurrectionRegistry,
    RareEventObservation,
    RequirementClosureLedger,
    RequirementProof,
    ResurrectionPoint,
    TailRiskLab,
    TelemetryAggregate,
    TelemetryFeedbackGate,
    TransformReceipt,
)


def _d(prefix: str) -> str:
    return prefix + "-" + "a" * 40


def _authority(
    evaluator_id: str,
    *evidence_refs: str,
) -> EvaluatorProvenance:
    refs = tuple(evidence_refs)
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=f"operation:{evaluator_id}",
        execution_id=f"execution:{evaluator_id}",
        execution_identity_digest=canonical_digest({"execution": evaluator_id}),
        finalization_intent_digest=canonical_digest({"finalization": evaluator_id}),
        authority_kind="deterministic_control",
        authority_identity_digest=canonical_digest({"authority": evaluator_id}),
        method_id="assurance-proof",
        source_revision=canonical_digest({"source": evaluator_id})[:40],
        output_evidence_refs=refs,
    )


def test_complexity_governor_requires_quality_density() -> None:
    gov = ComplexityGovernor(max_weighted_complexity=1000, minimum_quality_per_complexity=0.01)
    before = ComplexitySnapshot(10, 10, 10, 1024)
    waste = ComplexitySnapshot(20, 20, 20, 2048)
    denied = gov.assess(before, waste, quality_before=0.8, quality_after=0.81)
    assert denied.allowed is False
    lean = ComplexitySnapshot(8, 8, 8, 1024)
    allowed = gov.assess(before, lean, quality_before=0.8, quality_after=0.81)
    assert allowed.allowed is True
    assert allowed.complexity_delta < 0


def test_requirement_closure_is_fail_closed() -> None:
    ledger = RequirementClosureLedger(("REQ-1", "REQ-2"))
    ledger.record(
        RequirementProof(
            "REQ-1",
            _d("artifact"),
            (_d("evidence"),),
            _authority("req-1-judge", _d("evidence")),
            critical=True,
        )
    )
    assert ledger.closed is False
    assert ledger.missing == ("REQ-2",)
    ledger.record(
        RequirementProof(
            "REQ-2",
            _d("artifact2"),
            (_d("evidence2"),),
            _authority("req-2-fail-judge", _d("evidence2")),
            passed=False,
        )
    )
    assert ledger.failed == ("REQ-2",)
    ledger.record(
        RequirementProof(
            "REQ-2",
            _d("artifact2"),
            (_d("evidence3"),),
            _authority("req-2-pass-judge", _d("evidence3")),
            passed=True,
        )
    )
    assert ledger.closed is True
    assert len(ledger.digest) == 64


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: RequirementProof(
                "REQ-X",
                _d("artifact-x"),
                (_d("evidence-x"),),
                _authority("req-x-judge", _d("evidence-x")),
                passed="false",
            ),
            "requirement proof passed state must be boolean",
        ),
        (
            lambda: RequirementProof(
                "REQ-X",
                _d("artifact-x"),
                (_d("evidence-x"),),
                _authority("req-x-critical-judge", _d("evidence-x")),
                critical="false",
            ),
            "requirement proof critical state must be boolean",
        ),
        (
            lambda: ConstraintResult(
                "C-X",
                "false",
                _d("constraint-x"),
                _authority("constraint-x-judge", _d("constraint-x")),
            ),
            "constraint passed state must be boolean",
        ),
        (
            lambda: ConstraintResult(
                "C-X",
                True,
                _d("constraint-x"),
                _authority("constraint-x-critical-judge", _d("constraint-x")),
                critical="false",
            ),
            "constraint critical state must be boolean",
        ),
    ],
)
def test_deep_assurance_rejects_truthy_non_boolean_authority_states(
    factory,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        factory()


def test_requirement_proof_rejects_unattributed_evidence() -> None:
    with pytest.raises(DeepAssuranceError, match="referenced by evaluator authority"):
        RequirementProof(
            "REQ-UNBOUND",
            _d("artifact-unbound"),
            (_d("evidence-unbound"),),
            _authority("req-unbound-judge", _d("other-evidence")),
        )


def test_constraint_rejects_unattributed_evidence() -> None:
    with pytest.raises(DeepAssuranceError, match="referenced by evaluator authority"):
        ConstraintResult(
            "C-UNBOUND",
            True,
            _d("constraint-unbound"),
            _authority("constraint-unbound-judge", _d("other-constraint")),
        )


def test_constraint_proof_extracts_blocking_conflict_core() -> None:
    proof = ConstraintProofSet()
    proof.add(
        ConstraintResult(
            "C1",
            True,
            _d("e1"),
            _authority("constraint-c1", _d("e1")),
        )
    )
    proof.add(
        ConstraintResult(
            "C2",
            False,
            _d("e2"),
            _authority("constraint-c2", _d("e2")),
            conflict_ids=("C3",),
        )
    )
    assert proof.promotable is False
    assert proof.conflict_core == ("C2", "C3")


def test_intent_preservation_rejects_silent_semantic_drift() -> None:
    gate = IntentPreservationGate(
        (
            IntentInvariant("player-fantasy", _d("fantasy")),
            IntentInvariant("violence-tone", _d("tone")),
        )
    )
    current = (
        IntentInvariant("player-fantasy", _d("fantasy")),
        IntentInvariant("violence-tone", _d("changed")),
    )
    assert gate.verify(current) == ("violence-tone",)


def test_hermetic_transform_requires_exact_reproduction_identity() -> None:
    registry = HermeticTransformRegistry()
    evidence = _d("transform-execution")
    receipt = TransformReceipt(
        _d("tool"),
        _d("input"),
        _d("config"),
        _d("output"),
        _d("env"),
        _authority("transform-executor", evidence),
        evidence,
    )
    registry.record(receipt)
    assert registry.reproduce(receipt.digest, receipt)
    drift_evidence = _d("transform-drift")
    drift = TransformReceipt(
        _d("tool"),
        _d("input"),
        _d("config"),
        _d("other-output"),
        _d("env"),
        _authority("transform-replay", drift_evidence),
        drift_evidence,
    )
    assert registry.reproduce(receipt.digest, drift) is False


def test_transform_receipt_rejects_unattributed_execution_evidence() -> None:
    with pytest.raises(DeepAssuranceError, match="referenced by executor authority"):
        TransformReceipt(
            _d("tool"),
            _d("input"),
            _d("config"),
            _d("output"),
            _d("env"),
            _authority("transform-wrong", _d("other-evidence")),
            _d("transform-execution"),
        )


def test_knowledge_firewall_quarantines_unknown_and_separates_reference_from_incorporation() -> None:
    fw = KnowledgeIngestionFirewall()
    with pytest.raises(DeepAssuranceError, match="quarantined or forbidden"):
        fw.admit(
            KnowledgeSource(
                "unknown-web",
                _d("content"),
                "unknown_quarantine",
                "community",
                _d("snapshot"),
            )
        )
    fw.admit(
        KnowledgeSource(
            "official-doc",
            _d("content2"),
            "facts_and_ideas_reference_only",
            "official_documentation",
            _d("snapshot2"),
            factual_only=True,
        )
    )
    assert fw.may_use_as_reference("official-doc")
    assert fw.may_incorporate_expression("official-doc") is False
    assert len(fw.snapshot_digest) == 64


def test_multiresolution_coverage_requires_every_declared_scale() -> None:
    coverage = GranularityCoverage(("pixel", "frame", "scene", "whole_game"))
    coverage.record("pixel", _d("p"))
    coverage.record("frame", _d("f"))
    coverage.record("scene", _d("s"))
    assert coverage.complete is False
    assert coverage.missing == ("whole_game",)
    coverage.record("whole_game", _d("g"))
    assert coverage.complete is True


def test_player_mental_model_gate_blocks_critical_false_teaching() -> None:
    blockers = PlayerMentalModelGate.blockers(
        (
            MentalModelProbe("parry", "timing-window", "timing-window", critical=True),
            MentalModelProbe("save", "manual-and-auto", "manual-only", critical=True),
        )
    )
    assert blockers == ("save",)


def test_interaction_matrix_requires_all_pairs() -> None:
    matrix = InteractionMatrix(("combat", "economy", "quests"))
    matrix.cover("combat", "economy")
    matrix.cover("economy", "quests")
    assert matrix.complete is False
    assert matrix.missing_pairs == (("combat", "quests"),)
    matrix.cover("quests", "combat")
    assert matrix.complete is True


def test_tail_risk_uses_conservative_upper_bound() -> None:
    unsafe = RareEventObservation("save-corruption", samples=100, critical_failures=0, threshold=0.01)
    safe = RareEventObservation("save-corruption", samples=1000, critical_failures=0, threshold=0.01)
    assert unsafe.passed is False
    assert safe.passed is True
    assert TailRiskLab.blockers((unsafe, safe)) == ("save-corruption",)


def test_telemetry_feedback_rejects_raw_identity_and_tiny_cohorts() -> None:
    assert not TelemetryFeedbackGate.admit(
        TelemetryAggregate("quit-rate", _d("cohort"), 100, 0.2, contains_raw_identifier=True)
    )
    assert not TelemetryFeedbackGate.admit(
        TelemetryAggregate("quit-rate", _d("cohort2"), 5, 0.2)
    )
    assert TelemetryFeedbackGate.admit(
        TelemetryAggregate("quit-rate", _d("cohort3"), 100, 0.2)
    )


def test_project_resurrection_is_exact_and_content_addressed() -> None:
    checkpoint_evidence = _d("checkpoint-evidence")
    point = ResurrectionPoint(
        _d("project"),
        _d("canon"),
        _d("graph"),
        _d("events"),
        _d("rights"),
        _authority("checkpoint-authority", checkpoint_evidence),
        checkpoint_evidence,
    )
    registry = ProjectResurrectionRegistry()
    digest = registry.register(point)
    assert len(digest) == 64
    verification_evidence = _d("recovery-verification")
    proof = registry.verify(
        digest,
        point,
        verifier_provenance=_authority(
            "recovery-verifier",
            verification_evidence,
        ),
        verification_evidence_digest=verification_evidence,
    )
    assert proof.passed is True
    assert canonical_digest(proof.proof_payload()) == proof.proof_digest


def test_project_resurrection_proof_rejects_unattributed_verification_evidence() -> None:
    checkpoint_evidence = _d("checkpoint-evidence")
    point = ResurrectionPoint(
        _d("project"),
        _d("canon"),
        _d("graph"),
        _d("events"),
        _d("rights"),
        _authority("checkpoint-authority", checkpoint_evidence),
        checkpoint_evidence,
    )
    registry = ProjectResurrectionRegistry()
    digest = registry.register(point)
    with pytest.raises(
        DeepAssuranceError,
        match="verification evidence must be referenced by verifier authority",
    ):
        registry.verify(
            digest,
            point,
            verifier_provenance=_authority(
                "wrong-recovery-verifier",
                _d("other-recovery-evidence"),
            ),
            verification_evidence_digest=_d("recovery-verification"),
        )


def test_resurrection_verification_rejects_self_consistent_false_pass_state() -> None:
    checkpoint_evidence = _d("checkpoint-evidence")
    original = ResurrectionPoint(
        _d("project"),
        _d("canon"),
        _d("graph"),
        _d("events"),
        _d("rights"),
        _authority("checkpoint-authority", checkpoint_evidence),
        checkpoint_evidence,
    )
    different = ResurrectionPoint(
        _d("project-other"),
        _d("canon"),
        _d("graph"),
        _d("events"),
        _d("rights"),
        _authority("checkpoint-authority-other", _d("checkpoint-other")),
        _d("checkpoint-other"),
    )
    verification_evidence = _d("recovery-verification")
    verifier = _authority("recovery-verifier", verification_evidence)
    payload = {
        "checkpoint_digest": original.digest,
        "passed": True,
        "reconstructed_digest": different.digest,
        "verification_evidence_digest": verification_evidence,
        "verifier_provenance_digest": verifier.digest,
    }
    from skeleton.ai.game_builder.deep_assurance import ResurrectionVerification

    with pytest.raises(
        DeepAssuranceError,
        match="passed state does not match reconstructed identity",
    ):
        ResurrectionVerification(
            checkpoint_digest=original.digest,
            reconstructed_digest=different.digest,
            passed=True,
            verifier_provenance=verifier,
            verification_evidence_digest=verification_evidence,
            proof_digest=canonical_digest(payload),
        )


def test_evidence_merkle_root_changes_on_append() -> None:
    ledger = EvidenceMerkleLedger()
    root0 = ledger.root
    root1 = ledger.append(
        _d("one"),
        evaluator_provenance=_authority("evidence-one", _d("one")),
    )
    root2 = ledger.append(
        _d("two"),
        evaluator_provenance=_authority("evidence-two", _d("two")),
    )
    assert root0 != root1 != root2
    assert len(root2) == 64


def test_closure_certificate_rejects_truthy_non_boolean_independent_verification() -> None:
    with pytest.raises(TypeError, match="closure independent verification state must be boolean"):
        ClosureCertificate(
            artifact_digest=_d("artifact"),
            canon_digest=_d("canon"),
            provenance_digest=_d("provenance"),
            evidence_root=_d("evidence"),
            family_ids=tuple(f"GB{i:02d}" for i in range(1, 51)),
            critical_plane_ids=("OP01",),
            verifier_provenance=_authority("closure-verifier", _d("closure-verify")),
            verification_evidence_digest=_d("closure-verify"),
            independently_verified="false",
        )


def test_closure_certificate_rejects_unattributed_verification_evidence() -> None:
    with pytest.raises(DeepAssuranceError, match="referenced by verifier authority"):
        ClosureCertificate(
            artifact_digest=_d("artifact"),
            canon_digest=_d("canon"),
            provenance_digest=_d("provenance"),
            evidence_root=_d("evidence"),
            family_ids=tuple(f"GB{i:02d}" for i in range(1, 51)),
            critical_plane_ids=("OP01",),
            verifier_provenance=_authority("closure-wrong-verifier", _d("other-evidence")),
            verification_evidence_digest=_d("closure-evidence"),
            independently_verified=True,
        )


def test_closure_certificate_requires_all_families_zero_critical_gaps_and_independent_verification() -> None:
    critical = tuple(f"OP{i:02d}" for i in (1, 2, 4, 5, 6, 11, 14, 15, 16, 22, 24, 25, 26, 27, 28, 29, 30, 43, 47, 48, 49, 50, 51, 54, 55, 60, 63, 64, 65, 66, 67, 69, 70, 75, 76, 78, 79, 80))
    cert = ClosureCertificate(
        artifact_digest=_d("artifact"),
        canon_digest=_d("canon"),
        provenance_digest=_d("provenance"),
        evidence_root=_d("evidence"),
        family_ids=tuple(f"GB{i:02d}" for i in range(1, 51)),
        critical_plane_ids=critical,
        verifier_provenance=_authority("closure-verifier", _d("closure-verify")),
        verification_evidence_digest=_d("closure-verify"),
        independently_verified=True,
    )
    cert.validate(required_critical_planes=critical)
    assert len(cert.digest) == 64

    broken = ClosureCertificate(
        artifact_digest=_d("artifact"),
        canon_digest=_d("canon"),
        provenance_digest=_d("provenance"),
        evidence_root=_d("evidence"),
        family_ids=tuple(f"GB{i:02d}" for i in range(1, 51)),
        critical_plane_ids=critical,
        unresolved_critical_gaps=("save-corruption",),
        verifier_provenance=_authority("closure-gap-verifier", _d("closure-gap-verify")),
        verification_evidence_digest=_d("closure-gap-verify"),
        independently_verified=True,
    )
    with pytest.raises(DeepAssuranceError, match="unresolved critical gaps"):
        broken.validate(required_critical_planes=critical)
