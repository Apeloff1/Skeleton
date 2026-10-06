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
_load("skeleton.ai.game_builder.dual_rival_forge", "skeleton/ai/game_builder/dual_rival_forge.py")

from skeleton.ai.game_builder.contracts import (  # noqa: E402
    ArtifactIdentity,
    Candidate,
    Challenge,
    EffortMode,
    EvaluatorProvenance,
    GateResult,
    PromotionReceipt,
    ProducerProvenance,
    QUALITY_AXES,
    Rival,
    Stage,
    canonical_digest,
)
from skeleton.ai.game_builder.dual_rival_forge import DualRivalForge, ForgeStateError  # noqa: E402


def _quality(value: float = 0.5, **updates: float) -> dict[str, float]:
    result = {axis: value for axis in QUALITY_AXES}
    result.update(updates)
    return result


def _producer_provenance(
    token: str,
    *,
    project_id: str = "project:test-game",
    run_id: str = "run:test-forge",
    artifact_ref: str | None = None,
    evidence_refs: tuple[str, ...] | None = None,
) -> ProducerProvenance:
    suffix = (token * 32)[:32]
    default_evidence_refs = (
        f"evidence-{suffix}",
        f"assumption-{suffix}",
        f"attack-{suffix}",
        f"counterexample-{suffix}",
    )
    return ProducerProvenance(
        project_id=project_id,
        run_id=run_id,
        operation_id=f"operation:{token}",
        execution_id=f"execution:{token}",
        execution_identity_digest=canonical_digest({"execution": token}),
        finalization_intent_digest=canonical_digest({"finalization": token}),
        model_identity_digest=canonical_digest({"model": token}),
        producer_behavior_digest=canonical_digest({"behavior": token}),
        source_revision=canonical_digest({"source": token})[:40],
        provider_receipt_refs=(f"provider-receipt:{token}",),
        output_artifact_refs=(artifact_ref or f"artifact-{suffix}",),
        output_evidence_refs=evidence_refs or default_evidence_refs,
    )


def _candidate(
    producer: str,
    token: str,
    *,
    quality: dict[str, float] | None = None,
    parents: tuple[str, ...] = (),
    project_id: str = "project:test-game",
    run_id: str = "run:test-forge",
) -> Candidate:
    suffix = (token * 32)[:32]
    return Candidate.create(
        producer_id=producer,
        producer_provenance=_producer_provenance(
            token,
            project_id=project_id,
            run_id=run_id,
        ),
        artifact=ArtifactIdentity(
            artifact_digest=f"artifact-{suffix}",
            canon_digest=f"canon-{suffix}",
            provenance_digest=f"provenance-{suffix}",
            family_id="GB03",
            level_id="GBL-021",
        ),
        quality=quality or _quality(),
        evidence_digests=(f"evidence-{suffix}",),
        assumption_digest=f"assumption-{suffix}",
        parent_candidate_digests=parents,
    )


def _challenge(challenger: Rival, target: Candidate, token: str) -> Challenge:
    improved = _candidate(challenger.value, token)
    return Challenge(
        challenger_id=challenger.value,
        target_candidate_digest=target.digest,
        attack_digest=f"attack-{(token * 32)[:32]}",
        improved_candidate=improved,
        counterexample_digests=(f"counterexample-{(token * 32)[:32]}",),
    )


def _evaluator_provenance(
    evaluator_id: str,
    *,
    method_id: str = "deterministic-gate",
    evidence_refs: tuple[str, ...] = ("authority-evidence-0000000000000000",),
) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=f"operation:{evaluator_id}",
        execution_id=f"execution:{evaluator_id}",
        execution_identity_digest=canonical_digest({"execution": evaluator_id}),
        finalization_intent_digest=canonical_digest({"finalization": evaluator_id}),
        authority_kind="ai_execution",
        authority_identity_digest=canonical_digest({"model": evaluator_id}),
        method_id=method_id,
        source_revision=canonical_digest({"source": evaluator_id})[:40],
        provider_receipt_refs=(f"provider-receipt:{evaluator_id}",),
        output_evidence_refs=evidence_refs,
    )


def _adjudicator(
    evaluator_id: str = "independent-judge",
) -> tuple[EvaluatorProvenance, str]:
    evidence = f"authority-{evaluator_id}-0000000000000000"
    return (
        _evaluator_provenance(
            evaluator_id,
            method_id="promotion-adjudication",
            evidence_refs=(evidence,),
        ),
        evidence,
    )


def _gates(*, passed: bool = True) -> tuple[GateResult, ...]:
    rows = []
    for gate_id, evidence in (
        ("rights", "evidence-rights-0000000000000000"),
        ("continuity", "evidence-canon-00000000000000000"),
        ("state", "evidence-state-000000000000000000"),
    ):
        evaluator_id = f"gate-{gate_id}-judge"
        rows.append(
            GateResult(
                gate_id,
                passed,
                evidence,
                evaluator_provenance=_evaluator_provenance(
                    evaluator_id,
                    evidence_refs=(evidence,),
                ),
            )
        )
    return tuple(rows)


def test_effort_modes_are_exact_and_have_three_stage_executions() -> None:
    assert EffortMode.FORGE_100.rounds == 100
    assert EffortMode.FORGE_1000.rounds == 1000
    assert EffortMode.FORGE_10000.rounds == 10000
    assert EffortMode.FORGE_100.stage_executions == 300
    assert EffortMode.FORGE_1000.stage_executions == 3000
    assert EffortMode.FORGE_10000.stage_executions == 30000


def test_stage_order_and_role_rotation_are_fail_closed() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "s"))
    with pytest.raises(ForgeStateError, match="attack submission is out of stage order"):
        forge.submit_attack(_challenge(Rival.B, _candidate(Rival.A.value, "a"), "b"))

    built = _candidate(Rival.A.value, "a")
    assert forge.submit_construct(built).stage is Stage.ATTACK_AND_IMPROVE
    with pytest.raises(ForgeStateError, match="construct submission is out of stage order"):
        forge.submit_construct(built)

    attack = _challenge(Rival.B, built, "b")
    assert forge.submit_attack(attack).stage is Stage.RECONCILE_AND_PROMOTE
    forge.reconcile(
        submitted=None,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=_gates(),
    )

    assert forge.completed_rounds == 1
    assert forge.builder is Rival.B
    assert forge.challenger is Rival.A
    assert forge.stage is Stage.CONSTRUCT


def test_compensable_only_gate_set_cannot_promote() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    receipt = forge.reconcile(
        submitted=challenge.improved_candidate,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=(
            GateResult(
                "advisory",
                True,
                "evidence-advisory-0000000000000000",
                evaluator_provenance=_evaluator_provenance(
                    "gate-advisory-judge",
                    evidence_refs=("evidence-advisory-0000000000000000",),
                ),
                non_compensable=False,
            ),
        ),
    )

    assert receipt.decision == "retain_incumbent"
    assert forge.champion.digest == incumbent.digest


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("passed", 1, "passed state must be boolean"),
        ("passed", "false", "passed state must be boolean"),
        ("non_compensable", 1, "non_compensable state must be boolean"),
        ("non_compensable", "false", "non_compensable state must be boolean"),
    ],
)
def test_gate_result_rejects_non_boolean_authority_states(
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = {
        "gate_id": "rights",
        "passed": True,
        "evidence_digest": "evidence-rights-0000000000000000",
        "evaluator_provenance": _evaluator_provenance(
            "gate-rights-judge",
            evidence_refs=("evidence-rights-0000000000000000",),
        ),
        "non_compensable": True,
    }
    kwargs[field] = value
    with pytest.raises(TypeError, match=message):
        GateResult(**kwargs)


def test_gate_rejects_evidence_not_emitted_by_evaluator_execution() -> None:
    provenance = _evaluator_provenance(
        "gate-substitution-judge",
        evidence_refs=("gate-produced-evidence-0000000000000",),
    )
    with pytest.raises(
        ValueError,
        match="gate evidence must be referenced by evaluator execution output",
    ):
        GateResult(
            "rights",
            True,
            "gate-substituted-evidence-0000000000",
            evaluator_provenance=provenance,
        )


def test_promotion_rejects_authority_evidence_not_emitted_by_adjudicator() -> None:
    incumbent = _candidate("seed", "authority-seed", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "authority-built", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "authority-challenge")
    forge.submit_attack(challenge)
    provenance, _ = _adjudicator("authority-judge")
    with pytest.raises(
        ValueError,
        match="promotion authority evidence must be referenced",
    ):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id="authority-judge",
            evaluator_provenance=provenance,
            authority_evidence_digest="authority-substituted-000000000000000",
            gate_results=_gates(),
        )


def test_duplicate_gate_ids_are_rejected_before_promotion() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    duplicate = GateResult(
        "rights",
        True,
        "evidence-rights-1111111111111111",
        evaluator_provenance=_evaluator_provenance(
            "gate-rights-duplicate",
            evidence_refs=("evidence-rights-1111111111111111",),
        ),
    )
    with pytest.raises(ValueError, match="unique gate ids"):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id="independent-judge",
            evaluator_provenance=_adjudicator("independent-judge")[0],
            authority_evidence_digest=_adjudicator("independent-judge")[1],
            gate_results=(_gates()[0], duplicate),
        )


def test_malformed_gate_object_is_rejected_before_promotion() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    with pytest.raises(TypeError, match="GateResult"):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id="independent-judge",
            evaluator_provenance=_adjudicator("independent-judge")[0],
            authority_evidence_digest=_adjudicator("independent-judge")[1],
            gate_results=(object(),),
        )


def test_construct_rejects_cross_project_candidate_injection() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "seed"))
    candidate = _candidate(
        Rival.A.value,
        "cross-project",
        project_id="project:other",
    )
    with pytest.raises(ForgeStateError, match="project_id does not match forge scope"):
        forge.submit_construct(candidate)


def test_attack_rejects_cross_run_candidate_injection() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "seed"))
    built = _candidate(Rival.A.value, "built")
    forge.submit_construct(built)
    improved = _candidate(
        Rival.B.value,
        "cross-run",
        run_id="run:other-forge",
    )
    cross_run_suffix = ("cross-run" * 32)[:32]
    challenge = Challenge(
        challenger_id=Rival.B.value,
        target_candidate_digest=built.digest,
        attack_digest=f"attack-{cross_run_suffix}",
        improved_candidate=improved,
        counterexample_digests=(f"counterexample-{cross_run_suffix}",),
    )
    with pytest.raises(ForgeStateError, match="run_id does not match forge scope"):
        forge.submit_attack(challenge)


def test_candidate_digest_commits_to_producer_provenance() -> None:
    base = _candidate(Rival.A.value, "provenance-base")
    altered = Candidate.create(
        producer_id=base.producer_id,
        producer_provenance=_producer_provenance(
            "provenance-altered",
            artifact_ref=base.artifact.artifact_digest,
            evidence_refs=base.producer_provenance.output_evidence_refs,
        ),
        artifact=base.artifact,
        quality=base.quality_map,
        evidence_digests=base.evidence_digests,
        assumption_digest=base.assumption_digest,
        parent_candidate_digests=base.parent_candidate_digests,
    )
    assert altered.artifact == base.artifact
    assert altered.digest != base.digest


def test_candidate_rejects_artifact_not_committed_by_execution() -> None:
    provenance = _producer_provenance("output-artifact")
    suffix = ("output-artifact" * 32)[:32]
    with pytest.raises(
        ValueError,
        match="artifact must be referenced by producer execution output",
    ):
        Candidate.create(
            producer_id=Rival.A.value,
            producer_provenance=provenance,
            artifact=ArtifactIdentity(
                artifact_digest="artifact-substituted-0000000000000000",
                canon_digest=f"canon-{suffix}",
                provenance_digest=f"provenance-{suffix}",
                family_id="GB03",
                level_id="GBL-021",
            ),
            quality=_quality(),
            evidence_digests=(f"evidence-{suffix}",),
            assumption_digest=f"assumption-{suffix}",
        )


def test_candidate_rejects_evidence_and_assumption_not_committed_by_execution() -> None:
    provenance = _producer_provenance("output-evidence")
    suffix = ("output-evidence" * 32)[:32]
    artifact = ArtifactIdentity(
        artifact_digest=f"artifact-{suffix}",
        canon_digest=f"canon-{suffix}",
        provenance_digest=f"provenance-{suffix}",
        family_id="GB03",
        level_id="GBL-021",
    )
    with pytest.raises(
        ValueError,
        match="evidence must be referenced by producer execution output",
    ):
        Candidate.create(
            producer_id=Rival.A.value,
            producer_provenance=provenance,
            artifact=artifact,
            quality=_quality(),
            evidence_digests=("evidence-substituted-000000000000000",),
            assumption_digest=f"assumption-{suffix}",
        )
    with pytest.raises(
        ValueError,
        match="assumption must be referenced by producer execution output",
    ):
        Candidate.create(
            producer_id=Rival.A.value,
            producer_provenance=provenance,
            artifact=artifact,
            quality=_quality(),
            evidence_digests=(f"evidence-{suffix}",),
            assumption_digest="assumption-substituted-0000000000000",
        )


def test_challenge_rejects_attack_or_counterexample_not_emitted_by_execution() -> None:
    target = _candidate(Rival.A.value, "challenge-target")
    improved = _candidate(Rival.B.value, "challenge-output")
    with pytest.raises(
        ValueError,
        match="attack must be referenced by challenger execution output",
    ):
        Challenge(
            challenger_id=Rival.B.value,
            target_candidate_digest=target.digest,
            attack_digest="attack-substituted-000000000000000000",
            improved_candidate=improved,
            counterexample_digests=(
                improved.producer_provenance.output_evidence_refs[-1],
            ),
        )
    suffix = ("challenge-output" * 32)[:32]
    with pytest.raises(
        ValueError,
        match="counterexamples must be referenced by challenger execution output",
    ):
        Challenge(
            challenger_id=Rival.B.value,
            target_candidate_digest=target.digest,
            attack_digest=f"attack-{suffix}",
            improved_candidate=improved,
            counterexample_digests=("counterexample-substituted-000000000000",),
        )


def test_output_binding_digest_changes_when_execution_refs_change() -> None:
    base = _producer_provenance("binding-digest")
    altered = _producer_provenance(
        "binding-digest",
        evidence_refs=base.output_evidence_refs + ("extra-evidence-0000000000000000",),
    )
    assert altered.finalization_intent_digest == base.finalization_intent_digest
    assert altered.output_binding_digest != base.output_binding_digest
    assert altered.digest != base.digest


def test_non_compensable_gate_failure_retains_incumbent() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.7))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    receipt = forge.reconcile(
        submitted=challenge.improved_candidate,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=_gates(passed=False),
    )
    assert receipt.decision == "retain_incumbent"
    assert forge.champion.digest == incumbent.digest


def test_pareto_safe_candidate_promotes_with_independent_judge() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    improved = _candidate(
        Rival.B.value,
        "b",
        quality=_quality(
            0.5,
            longform_consistency=0.6,
            rights_provenance_safety=0.7,
        ),
    )
    forge.submit_attack(
        Challenge(
            challenger_id=Rival.B.value,
            target_candidate_digest=built.digest,
            attack_digest="attack-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            improved_candidate=improved,
            counterexample_digests=("counterexample-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",),
        )
    )
    receipt = forge.reconcile(
        submitted=improved,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=_gates(),
    )
    assert receipt.decision == "promote"
    assert forge.champion.digest == improved.digest


@pytest.mark.parametrize("evaluator", [Rival.A.value, Rival.B.value])
def test_rivals_cannot_be_final_promotion_judge(evaluator: str) -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "s"))
    built = _candidate(Rival.A.value, "a")
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)
    with pytest.raises(ValueError, match="independent"):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id=evaluator,
            evaluator_provenance=_adjudicator(evaluator)[0],
            authority_evidence_digest=_adjudicator(evaluator)[1],
            gate_results=_gates(),
        )


def test_synthesis_requires_both_parent_candidates_and_non_rival_identity() -> None:
    forge = DualRivalForge(
        effort_mode=100,
        champion=_candidate("seed", "s", quality=_quality(0.3)),
    )
    built = _candidate(Rival.A.value, "a", quality=_quality(0.4))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    bad = _candidate("synthesis", "x", quality=_quality(0.6), parents=(built.digest,))
    with pytest.raises(ForgeStateError, match="must name both"):
        forge.reconcile(
            submitted=bad,
            evaluator_id="independent-judge",
            evaluator_provenance=_adjudicator("independent-judge")[0],
            authority_evidence_digest=_adjudicator("independent-judge")[1],
            gate_results=_gates(),
        )

    synthesis = _candidate(
        "synthesis:rival_a+rival_b",
        "y",
        quality=_quality(0.6),
        parents=(built.digest, challenge.improved_candidate.digest),
    )
    receipt = forge.reconcile(
        submitted=synthesis,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=_gates(),
    )
    assert receipt.decision == "promote"
    assert forge.champion.digest == synthesis.digest


def test_checkpoint_round_trip_preserves_pending_attack_state() -> None:
    forge = DualRivalForge(effort_mode="forge_1000", champion=_candidate("seed", "s"))
    built = _candidate(Rival.A.value, "a")
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    checkpoint = forge.checkpoint()
    restored = DualRivalForge.restore(
        checkpoint,
        expected_checkpoint_digest=checkpoint["checkpoint_digest"],
    )

    assert restored.status.to_payload() == forge.status.to_payload()
    assert restored.pending_construct is not None
    assert restored.pending_construct.digest == built.digest
    assert restored.pending_challenge is not None
    assert restored.pending_challenge.digest == challenge.digest

    tampered = dict(checkpoint)
    tampered["round_index"] = 999
    with pytest.raises(ForgeStateError, match="checkpoint digest mismatch"):
        DualRivalForge.restore(
            tampered,
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
        )


def test_trusted_checkpoint_rejects_boolean_quality_coercion() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "quality-seed"))
    built = _candidate(Rival.A.value, "quality-built")
    forge.submit_construct(built)
    checkpoint = forge.checkpoint()
    tampered = {
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_digest"
    }
    pending = dict(tampered["pending_construct"])
    quality = dict(pending["quality"])
    quality["player_value"] = True
    pending["quality"] = quality
    tampered["pending_construct"] = pending
    tampered["checkpoint_digest"] = canonical_digest(tampered)

    with pytest.raises(ForgeStateError, match="quality values must be numeric"):
        DualRivalForge.restore(
            tampered,
            expected_checkpoint_digest=tampered["checkpoint_digest"],
        )


def test_v1_checkpoint_schema_is_rejected_after_provenance_upgrade() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "schema-seed"))
    checkpoint = forge.checkpoint()
    legacy = {
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_digest"
    }
    legacy["schema"] = "skeleton.ai_game_builder.dual_rival_checkpoint.v1"
    legacy["checkpoint_digest"] = canonical_digest(legacy)

    with pytest.raises(ForgeStateError, match="unsupported checkpoint schema"):
        DualRivalForge.restore(
            legacy,
            expected_checkpoint_digest=legacy["checkpoint_digest"],
        )


def test_promotion_receipt_rehashes_public_decision_evidence() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)
    receipt = forge.reconcile(
        submitted=challenge.improved_candidate,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=_gates(),
    )

    assert canonical_digest(receipt.decision_payload()) == receipt.decision_digest
    with pytest.raises(ValueError, match="decision digest mismatch"):
        PromotionReceipt(
            round_index=receipt.round_index,
            effort_mode=receipt.effort_mode,
            incumbent_digest=receipt.incumbent_digest,
            submitted_digest=receipt.submitted_digest,
            promoted_digest=receipt.promoted_digest,
            evaluator_id=receipt.evaluator_id,
            evaluator_provenance=receipt.evaluator_provenance,
            authority_evidence_digest=receipt.authority_evidence_digest,
            gate_results=receipt.gate_results,
            evaluated_submitted_quality=receipt.evaluated_submitted_quality,
            evaluation_decision_digest=receipt.evaluation_decision_digest,
            decision=receipt.decision,
            decision_digest="tampered-" + "0" * 64,
        )


def test_forge_rejects_completed_round_count_without_receipt_history() -> None:
    with pytest.raises(
        ForgeStateError,
        match="completed_rounds must equal promotion receipt count",
    ):
        DualRivalForge(
            effort_mode=100,
            champion=_candidate("seed", "s"),
            completed_rounds=1,
            round_index=2,
        )


def test_forge_rejects_terminal_champion_not_bound_to_receipt_chain() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)
    receipt = forge.reconcile(
        submitted=None,
        evaluator_id="independent-judge",
        evaluator_provenance=_adjudicator("independent-judge")[0],
        authority_evidence_digest=_adjudicator("independent-judge")[1],
        gate_results=_gates(),
    )

    with pytest.raises(
        ForgeStateError,
        match="forge champion must match terminal promotion receipt",
    ):
        DualRivalForge(
            effort_mode=100,
            champion=_candidate("seed", "different"),
            builder=Rival.B,
            completed_rounds=1,
            round_index=2,
            receipts=(receipt,),
        )


def test_self_consistent_forged_checkpoint_cannot_invent_completed_rounds() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "s"))
    checkpoint = forge.checkpoint()
    forged = {
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_digest"
    }
    forged["completed_rounds"] = 1
    forged["round_index"] = 2
    forged["receipt_digests"] = []
    forged["checkpoint_digest"] = canonical_digest(
        {key: value for key, value in forged.items() if key != "checkpoint_digest"}
    )

    with pytest.raises(
        ForgeStateError,
        match="trusted external anchor",
    ):
        DualRivalForge.restore(
            forged,
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
        )


def test_checkpoint_scope_substitution_is_rejected_even_when_rehashed() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "scope-check"))
    checkpoint = forge.checkpoint()
    tampered = {
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_digest"
    }
    tampered["project_id"] = "project:substituted"
    tampered["checkpoint_digest"] = canonical_digest(
        {key: value for key, value in tampered.items() if key != "checkpoint_digest"}
    )
    with pytest.raises(ForgeStateError, match="trusted external anchor"):
        DualRivalForge.restore(
            tampered,
            expected_checkpoint_digest=checkpoint["checkpoint_digest"],
        )


def test_forge_100_completes_only_after_exactly_100_three_stage_rounds() -> None:
    forge = DualRivalForge(
        effort_mode=EffortMode.FORGE_100,
        champion=_candidate("seed", "s"),
    )
    for round_number in range(1, 101):
        builder = forge.builder
        challenger = forge.challenger
        built = _candidate(builder.value, f"a{round_number}")
        forge.submit_construct(built)
        forge.submit_attack(_challenge(challenger, built, f"b{round_number}"))
        forge.reconcile(
            submitted=None,
            evaluator_id="independent-judge",
            evaluator_provenance=_adjudicator("independent-judge")[0],
            authority_evidence_digest=_adjudicator("independent-judge")[1],
            gate_results=_gates(),
        )
        assert forge.completed_rounds == round_number

    assert forge.completed is True
    assert forge.completed_rounds == 100
    assert forge.status.remaining_rounds == 0
    with pytest.raises(ForgeStateError, match="round budget is complete"):
        forge.submit_construct(_candidate(forge.builder.value, "final"))
