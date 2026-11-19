from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.learning.promotion_control import (
    CanaryEvidence,
    EvaluationBundle,
    ImprovementCandidate,
    ImprovementError,
    PromotionDecision,
    PromotionLedger,
    PromotionStatus,
    RollbackReceipt,
    decide,
    promote_with_canary,
    validate_rollback,
)


def S(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def candidate(**overrides) -> ImprovementCandidate:
    values = dict(
        candidate_id="CANDIDATE.101",
        champion_digest=S("champion"),
        challenger_digest=S("challenger"),
        experiment_scope="isolated:forge",
        metric_ids=("METRIC.QUALITY",),
        builder_id="ACTOR.BUILDER",
    )
    values.update(overrides)
    return ImprovementCandidate(**values)


def evaluation(
    candidate_value: ImprovementCandidate | None = None,
    **overrides,
) -> EvaluationBundle:
    selected = candidate_value or candidate()
    values = dict(
        candidate_digest=selected.digest,
        metric_values=(("METRIC.QUALITY", 0.9),),
        safety_passed=True,
        cost_passed=True,
        robustness_passed=True,
        evidence_digest=S("eval"),
    )
    values.update(overrides)
    return EvaluationBundle(**values)


def canary(
    candidate_value: ImprovementCandidate | None = None,
    **overrides,
) -> CanaryEvidence:
    selected = candidate_value or candidate()
    values = dict(
        candidate_digest=selected.digest,
        canary_digest=S("canary-run"),
        safety_passed=True,
        quality_passed=True,
        rollback_ready=True,
        verifier_id="ACTOR.CANARY",
    )
    values.update(overrides)
    return CanaryEvidence(**values)


def promoted_decision(
    candidate_value: ImprovementCandidate | None = None,
) -> PromotionDecision:
    selected = candidate_value or candidate()
    return promote_with_canary(
        selected,
        evaluation(selected),
        "ACTOR.VERIFIER",
        canary(selected),
    )


def verified_promotion(
    candidate_value: ImprovementCandidate | None = None,
):
    selected = candidate_value or candidate()
    evaluation_value = evaluation(selected)
    canary_value = canary(selected)
    decision_value = promote_with_canary(
        selected,
        evaluation_value,
        "ACTOR.VERIFIER",
        canary_value,
    )
    return evaluation_value, canary_value, decision_value


def rollback_receipt(
    candidate_value: ImprovementCandidate,
    decision_value: PromotionDecision,
    *,
    verifier_id: str = "ACTOR.ROLLBACK",
    decision_digest: str | None = None,
    restored_digest: str | None = None,
) -> RollbackReceipt:
    return RollbackReceipt(
        decision_id=decision_value.decision_id,
        promoted_digest=candidate_value.challenger_digest,
        restored_digest=(
            candidate_value.champion_digest
            if restored_digest is None
            else restored_digest
        ),
        rollback_evidence_digest=S("rollback-evidence"),
        decision_digest=(
            decision_value.digest
            if decision_digest is None
            else decision_digest
        ),
        verifier_id=verifier_id,
    )


def test_candidate_requires_distinct_challenger() -> None:
    with pytest.raises(ImprovementError, match="differ"):
        ImprovementCandidate(
            "CANDIDATE.X",
            S("same"),
            S("same"),
            "scope",
            ("METRIC.X",),
            "ACTOR.B",
        )


def test_candidate_rejects_duplicate_preregistered_metrics() -> None:
    base = candidate()
    with pytest.raises(ImprovementError, match="duplicate predeclared"):
        ImprovementCandidate(
            "CANDIDATE.X",
            base.champion_digest,
            base.challenger_digest,
            "scope",
            ("METRIC.X", "METRIC.X"),
            "ACTOR.B",
        )


def test_candidate_metric_collection_is_bounded_tuple() -> None:
    base = candidate()
    with pytest.raises(ImprovementError, match="bounded tuple"):
        ImprovementCandidate(
            "CANDIDATE.X",
            base.champion_digest,
            base.challenger_digest,
            "scope",
            ["METRIC.X"],  # type: ignore[arg-type]
            "ACTOR.B",
        )


def test_candidate_scope_must_be_normalized() -> None:
    with pytest.raises(ImprovementError, match="normalized"):
        candidate(experiment_scope=" isolated:forge")


def test_candidate_digest_is_canonical_for_metric_order() -> None:
    first = candidate(
        metric_ids=("METRIC.QUALITY", "METRIC.COST")
    )
    second = candidate(
        metric_ids=("METRIC.COST", "METRIC.QUALITY")
    )
    assert first.digest == second.digest
    assert first.metric_ids == second.metric_ids


def test_self_promotion_rejected() -> None:
    selected = candidate()
    with pytest.raises(ImprovementError, match="independent"):
        promote_with_canary(
            selected,
            evaluation(selected),
            selected.builder_id,
            canary(selected),
        )


def test_metric_substitution_rejected() -> None:
    selected = candidate()
    bundle = evaluation(
        selected,
        metric_values=(("METRIC.OTHER", 1.0),),
    )
    with pytest.raises(ImprovementError, match="preregistration"):
        decide(
            selected,
            bundle,
            "ACTOR.VERIFIER",
            canary_digest=None,
        )


@pytest.mark.parametrize(
    "field",
    ["safety_passed", "cost_passed", "robustness_passed"],
)
def test_failed_evaluation_gate_rejects_candidate(field: str) -> None:
    selected = candidate()
    decision = decide(
        selected,
        evaluation(selected, **{field: False}),
        "ACTOR.VERIFIER",
        canary_digest=None,
    )
    assert decision.status is PromotionStatus.REJECT
    assert field.replace("_passed", "") in decision.reason
    assert decision.canary_digest is None
    assert decision.canary_verifier_id is None


def test_passing_evaluation_requires_typed_canary_evidence() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="verified canary evidence",
    ):
        decide(
            selected,
            evaluation(selected),
            "ACTOR.VERIFIER",
            canary_digest=None,
        )


def test_raw_canary_digest_cannot_authorize_promotion() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="raw canary digest cannot authorize",
    ):
        decide(
            selected,
            evaluation(selected),
            "ACTOR.VERIFIER",
            canary_digest=S("forged-canary"),
        )


def test_rejected_evaluation_cannot_smuggle_canary_authority() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="rejected evaluation cannot carry",
    ):
        decide(
            selected,
            evaluation(selected, safety_passed=False),
            "ACTOR.VERIFIER",
            canary_digest=S("canary"),
        )


def test_valid_independent_promotion_binds_full_canary_evidence() -> None:
    selected = candidate()
    canary_evidence = canary(selected)
    decision = promote_with_canary(
        selected,
        evaluation(selected),
        "ACTOR.VERIFIER",
        canary_evidence,
    )
    assert decision.status is PromotionStatus.PROMOTE
    assert decision.canary_digest == canary_evidence.digest
    assert decision.canary_verifier_id == canary_evidence.verifier_id
    assert decision.reason == ""


def test_canary_candidate_mismatch_is_rejected() -> None:
    selected = candidate()
    other = canary(
        selected,
        candidate_digest=S("other"),
    )
    with pytest.raises(ImprovementError, match="canary/candidate"):
        promote_with_canary(
            selected,
            evaluation(selected),
            "ACTOR.VERIFIER",
            other,
        )


@pytest.mark.parametrize(
    "field",
    ["safety_passed", "quality_passed", "rollback_ready"],
)
def test_canary_requires_all_gates(field: str) -> None:
    selected = candidate()
    failed = canary(selected, **{field: False})
    with pytest.raises(ImprovementError, match="canary gates"):
        promote_with_canary(
            selected,
            evaluation(selected),
            "ACTOR.VERIFIER",
            failed,
        )


def test_canary_verifier_must_be_independent_from_builder() -> None:
    selected = candidate()
    self_canary = canary(
        selected,
        verifier_id=selected.builder_id,
    )
    with pytest.raises(
        ImprovementError,
        match="independent from builder",
    ):
        promote_with_canary(
            selected,
            evaluation(selected),
            "ACTOR.VERIFIER",
            self_canary,
        )


def test_canary_verifier_must_differ_from_promotion_verifier() -> None:
    selected = candidate()
    same_verifier = canary(
        selected,
        verifier_id="ACTOR.VERIFIER",
    )
    with pytest.raises(
        ImprovementError,
        match="differ from promotion verifier",
    ):
        promote_with_canary(
            selected,
            evaluation(selected),
            "ACTOR.VERIFIER",
            same_verifier,
        )


def test_evaluation_rejects_duplicate_nonfinite_and_boolean_metrics() -> None:
    selected = candidate()
    with pytest.raises(ImprovementError, match="duplicate"):
        evaluation(
            selected,
            metric_values=(
                ("METRIC.QUALITY", 0.9),
                ("METRIC.QUALITY", 0.8),
            ),
        )
    with pytest.raises(ImprovementError, match="finite numeric"):
        evaluation(
            selected,
            metric_values=(("METRIC.QUALITY", float("nan")),),
        )
    with pytest.raises(ImprovementError, match="finite numeric"):
        evaluation(
            selected,
            metric_values=(("METRIC.QUALITY", True),),
        )


def test_evaluation_rejects_malformed_metric_rows() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="entries must be",
    ):
        evaluation(
            selected,
            metric_values=(("METRIC.QUALITY", 0.9, 1.0),),  # type: ignore[arg-type]
        )


def test_promotion_gates_are_strict_booleans() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="safety_passed must be bool",
    ):
        evaluation(selected, safety_passed=1)
    with pytest.raises(
        ImprovementError,
        match="cost_passed must be bool",
    ):
        evaluation(selected, cost_passed="yes")


def test_evaluation_digest_binds_gate_outcomes_and_metrics() -> None:
    selected = candidate()
    first = evaluation(selected)
    changed_metric = evaluation(
        selected,
        metric_values=(("METRIC.QUALITY", 0.8),),
    )
    changed_gate = evaluation(
        selected,
        robustness_passed=False,
    )
    assert first.digest != changed_metric.digest
    assert first.digest != changed_gate.digest


def test_promotion_decision_digest_is_deterministic() -> None:
    selected = candidate()
    first = promoted_decision(selected)
    second = promoted_decision(selected)
    assert first == second
    assert first.digest == second.digest


def test_rejected_decision_requires_reason() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="requires reason",
    ):
        PromotionDecision(
            decision_id="DECISION.CANDIDATE.101",
            candidate_digest=selected.digest,
            verifier_id="ACTOR.VERIFIER",
            status=PromotionStatus.REJECT,
            evaluation_digest=S("evaluation"),
            canary_digest=None,
            reason="",
        )


def test_rejected_decision_cannot_carry_canary_authority() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="cannot carry",
    ):
        PromotionDecision(
            decision_id="DECISION.CANDIDATE.101",
            candidate_digest=selected.digest,
            verifier_id="ACTOR.VERIFIER",
            status=PromotionStatus.REJECT,
            evaluation_digest=S("evaluation"),
            canary_digest=S("canary"),
            canary_verifier_id="ACTOR.CANARY",
            reason="failed gates: safety",
        )


def test_promoted_decision_requires_canary_verifier_identity() -> None:
    selected = candidate()
    with pytest.raises(
        ImprovementError,
        match="verified canary",
    ):
        PromotionDecision(
            decision_id="DECISION.CANDIDATE.101",
            candidate_digest=selected.digest,
            verifier_id="ACTOR.VERIFIER",
            status=PromotionStatus.PROMOTE,
            evaluation_digest=S("evaluation"),
            canary_digest=S("canary"),
            canary_verifier_id=None,
        )


def test_rollback_must_restore_exact_champion_for_exact_promotion() -> None:
    selected = candidate()
    decision = promoted_decision(selected)
    good = rollback_receipt(selected, decision)
    validate_rollback(selected, decision, good)

    wrong = rollback_receipt(
        selected,
        decision,
        restored_digest=S("other"),
    )
    with pytest.raises(
        ImprovementError,
        match="exact champion",
    ):
        validate_rollback(selected, decision, wrong)


def test_rollback_must_bind_exact_promotion_decision_digest() -> None:
    selected = candidate()
    decision = promoted_decision(selected)
    missing = RollbackReceipt(
        decision_id=decision.decision_id,
        promoted_digest=selected.challenger_digest,
        restored_digest=selected.champion_digest,
        rollback_evidence_digest=S("rollback"),
        decision_digest=None,
        verifier_id="ACTOR.ROLLBACK",
    )
    with pytest.raises(
        ImprovementError,
        match="bind exact promotion decision",
    ):
        validate_rollback(selected, decision, missing)

    wrong = rollback_receipt(
        selected,
        decision,
        decision_digest=S("another-decision"),
    )
    with pytest.raises(
        ImprovementError,
        match="decision digest mismatch",
    ):
        validate_rollback(selected, decision, wrong)


def test_rollback_requires_fourth_independent_verifier() -> None:
    selected = candidate()
    evaluation_value, canary_value, decision = verified_promotion(selected)
    ledger.record_decision(
        selected,
        decision,
        evaluation=evaluation_value,
        canary=canary_value,
    )
    for verifier in (
        selected.builder_id,
        decision.verifier_id,
        decision.canary_verifier_id,
    ):
        receipt = rollback_receipt(
            selected,
            decision,
            verifier_id=verifier,
        )
        with pytest.raises(
            ImprovementError,
            match="independently separated",
        ):
            validate_rollback(selected, decision, receipt)


def test_rejected_candidate_cannot_claim_promotion_rollback() -> None:
    selected = candidate()
    decision = decide(
        selected,
        evaluation(selected, safety_passed=False),
        "ACTOR.VERIFIER",
        canary_digest=None,
    )
    receipt = RollbackReceipt(
        decision_id=decision.decision_id,
        promoted_digest=selected.challenger_digest,
        restored_digest=selected.champion_digest,
        rollback_evidence_digest=S("rollback"),
        decision_digest=decision.digest,
        verifier_id="ACTOR.ROLLBACK",
    )
    with pytest.raises(
        ImprovementError,
        match="promoted candidate",
    ):
        validate_rollback(selected, decision, receipt)


def test_promotion_ledger_rejects_manually_forged_promote_decision() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    evaluation_value = evaluation(selected)
    canary_value = canary(selected)
    legitimate = promote_with_canary(
        selected,
        evaluation_value,
        "ACTOR.VERIFIER",
        canary_value,
    )
    forged = replace(
        legitimate,
        evaluation_digest=S("forged-evaluation"),
    )
    with pytest.raises(
        ImprovementError,
        match="does not match supplied evaluation/canary evidence",
    ):
        ledger.record_decision(
            selected,
            forged,
            evaluation=evaluation_value,
            canary=canary_value,
        )


def test_promotion_ledger_rollback_requires_preverified_decision() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    decision = promoted_decision(selected)
    with pytest.raises(
        ImprovementError,
        match="must be evidence-verified before rollback",
    ):
        ledger.record_rollback(
            selected,
            decision,
            rollback_evidence_digest=S("rollback"),
            verifier_id="ACTOR.ROLLBACK",
        )


def test_promotion_ledger_candidate_id_is_immutable() -> None:
    ledger = PromotionLedger()
    first = candidate()
    ledger.register_candidate(first)
    rebound = candidate(
        challenger_digest=S("different-challenger"),
    )
    with pytest.raises(
        ImprovementError,
        match="candidate id is already bound",
    ):
        ledger.register_candidate(rebound)


def test_promotion_ledger_decision_is_idempotent_but_not_rebindable() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    evaluation_value, canary_value, decision = verified_promotion(selected)
    assert ledger.record_decision(
        selected,
        decision,
        evaluation=evaluation_value,
        canary=canary_value,
    ) == decision
    assert ledger.record_decision(
        selected,
        decision,
        evaluation=evaluation_value,
        canary=canary_value,
    ) == decision

    altered = replace(
        decision,
        evaluation_digest=S("different-evaluation"),
    )
    with pytest.raises(
        ImprovementError,
        match="already bound to another decision",
    ):
        ledger.record_decision(
            selected,
            altered,
            evaluation=evaluation_value,
            canary=canary_value,
        )


def test_promotion_ledger_rejects_wrong_decision_id() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    evaluation_value, canary_value, base_decision = verified_promotion(selected)
    decision = replace(
        base_decision,
        decision_id="DECISION.OTHER",
    )
    with pytest.raises(
        ImprovementError,
        match="does not match candidate",
    ):
        ledger.record_decision(
            selected,
            decision,
            evaluation=evaluation_value,
            canary=canary_value,
        )


def test_promotion_ledger_records_independent_rollback_once() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    evaluation_value, canary_value, decision = verified_promotion(selected)
    ledger.record_decision(
        selected,
        decision,
        evaluation=evaluation_value,
        canary=canary_value,
    )
    receipt = ledger.record_rollback(
        selected,
        decision,
        rollback_evidence_digest=S("rollback-evidence"),
        verifier_id="ACTOR.ROLLBACK",
    )
    assert receipt.decision_digest == decision.digest
    assert receipt.verifier_id == "ACTOR.ROLLBACK"
    validate_rollback(selected, decision, receipt)

    replay = ledger.record_rollback(
        selected,
        decision,
        rollback_evidence_digest=S("rollback-evidence"),
        verifier_id="ACTOR.ROLLBACK",
    )
    assert replay == receipt


def test_promotion_ledger_rollback_rebinding_fails_closed() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    evaluation_value, canary_value, decision = verified_promotion(selected)
    ledger.record_decision(
        selected,
        decision,
        evaluation=evaluation_value,
        canary=canary_value,
    )
    ledger.record_rollback(
        selected,
        decision,
        rollback_evidence_digest=S("rollback-a"),
        verifier_id="ACTOR.ROLLBACK",
    )
    with pytest.raises(
        ImprovementError,
        match="already bound to another receipt",
    ):
        ledger.record_rollback(
            selected,
            decision,
            rollback_evidence_digest=S("rollback-b"),
            verifier_id="ACTOR.ROLLBACK",
        )


def test_promotion_ledger_rejects_nonindependent_rollback_verifier() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    decision = promoted_decision(selected)
    for verifier in (
        selected.builder_id,
        decision.verifier_id,
        decision.canary_verifier_id,
    ):
        with pytest.raises(
            ImprovementError,
            match="independently separated",
        ):
            ledger.record_rollback(
                selected,
                decision,
                rollback_evidence_digest=S("rollback"),
                verifier_id=verifier,
            )


def test_promotion_ledger_audit_digest_changes_on_decision_and_rollback() -> None:
    ledger = PromotionLedger()
    selected = candidate()
    before = ledger.audit_chain_digest
    evaluation_value, canary_value, decision = verified_promotion(selected)
    ledger.record_decision(
        selected,
        decision,
        evaluation=evaluation_value,
        canary=canary_value,
    )
    after_decision = ledger.audit_chain_digest
    ledger.record_rollback(
        selected,
        decision,
        rollback_evidence_digest=S("rollback"),
        verifier_id="ACTOR.ROLLBACK",
    )
    after_rollback = ledger.audit_chain_digest

    assert before != after_decision
    assert after_decision != after_rollback
