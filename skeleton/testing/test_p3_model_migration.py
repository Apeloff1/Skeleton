"""Evidence, compensation, budget and concurrency gates for candidate migration."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest

from skeleton.ai.runtime.learning_foundation.lifecycle import (
    MigrationParityCase,
    ModelBillOfMaterials,
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _mbom(name: str) -> ModelBillOfMaterials:
    return ModelBillOfMaterials(
        model_id=name,
        model_digest=_sha(name),
        artifact_digest=_sha(f"artifact:{name}"),
        artifact_kind="fixture",
        training_run_id=f"run:{name}",
        training_receipt_digest=_sha(f"training:{name}"),
        dataset_digests=(_sha("dataset"),),
        trainer_id=f"trainer:{name}",
        code_revision="fixture-revision",
        license_refs=("license:apache-2.0",),
        rights_refs=("rights:train-evaluate",),
    )


def _registry(**budgets):
    registry = ModelLifecycleRegistry(**budgets)
    source = registry.register_candidate(_mbom("source"))
    target = registry.register_candidate(_mbom("target"))
    for mbom in (source, target):
        registry.transition(
            mbom.model_digest,
            ModelLifecycleState.VALIDATED,
            verifier_id="validation-verifier",
            evidence_refs=("eval:quality", "eval:safety"),
        )
    registry.transition(
        source.model_digest,
        ModelLifecycleState.ACTIVE,
        verifier_id="activation-verifier",
        evidence_refs=("canary:baseline", "rollback:baseline"),
    )
    return registry, source, target


def _cases(*, matches=(True, True, True)):
    return tuple(
        MigrationParityCase(
            case_id=f"case:{index}",
            input_digest=_sha(f"input:{index}"),
            source_output_digest=_sha(f"output:{index}"),
            target_output_digest=_sha(f"output:{index}" if match else f"changed:{index}"),
        )
        for index, match in enumerate(matches)
    )


def _decision(registry, source, target, **overrides):
    arguments = {
        "source_model_digest": source.model_digest,
        "target_model_digest": target.model_digest,
        "cases": _cases(),
        "required_score": 1.0,
        "verifier_id": "migration-verifier",
        "evaluation_refs": ("eval:parity", "eval:regression"),
    }
    return registry.evaluate_migration(**(arguments | overrides))


def _rollback(registry, migration, **overrides):
    arguments = {
        "verifier_id": "rollback-verifier",
        "evidence_refs": ("incident:regression", "restore:baseline"),
    }
    return registry.rollback_migration(migration, **(arguments | overrides))


def test_parity_derived_from_cases_and_bound_to_exact_mbom_and_lifecycle():
    registry, source, target = _registry()
    decision = _decision(
        registry, source, target, cases=_cases(matches=(True, False, True)), required_score=0.6
    )
    evidence = registry.migration_evaluation(decision)
    assert decision.approved and decision.parity_score == 2 / 3
    assert evidence.source_mbom_digest == source.digest
    assert evidence.target_mbom_digest == target.digest
    assert evidence.source_lifecycle_digest == registry.lifecycle_digest(source.model_digest)
    assert evidence.target_lifecycle_digest == registry.lifecycle_digest(target.model_digest)
    assert (
        _decision(registry, source, target, cases=_cases(matches=(True, False, True)), required_score=0.6)
        is decision
    )


def test_apply_and_rollback_preserve_original_history_and_restore_baseline():
    registry, source, target = _registry()
    initial = registry.history
    decision = _decision(registry, source, target)
    migration = registry.apply_migration(decision)
    assert registry.state(source.model_digest) is ModelLifecycleState.DEPRECATED
    assert registry.state(target.model_digest) is ModelLifecycleState.ACTIVE
    assert migration.rollback_model_digest == source.model_digest
    assert migration.evaluation_digest == registry.migration_evaluation(decision).evaluation_digest
    assert registry.history == initial + migration.transitions
    rollback = _rollback(registry, migration)
    assert registry.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert registry.state(target.model_digest) is ModelLifecycleState.VALIDATED
    assert registry.history == initial + migration.transitions + rollback.transitions
    assert registry.migrations == (migration,)
    assert registry.rollbacks == (rollback,)
    assert rollback.transitions[0].from_state == "deprecated"
    assert rollback.transitions[0].to_state == "active"
    with pytest.raises(FrozenInstanceError):
        migration.verifier_id = "changed"


def test_apply_and_rollback_replays_return_receipts_without_reapplying():
    registry, source, target = _registry()
    decision = _decision(registry, source, target)
    migration = registry.apply_migration(decision)
    assert registry.apply_migration(decision) is migration
    rollback = _rollback(registry, migration)
    history = registry.history
    assert _rollback(registry, migration) is rollback
    assert registry.apply_migration(decision) is migration
    assert registry.history == history
    assert registry.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert registry.state(target.model_digest) is ModelLifecycleState.VALIDATED


def test_numeric_approved_proposal_does_not_authorize_migration():
    registry, source, target = _registry()
    proposal = registry.migration_decision(
        source_model_digest=source.model_digest,
        target_model_digest=target.model_digest,
        parity_score=1.0,
        required_score=1.0,
        verifier_id="migration-verifier",
        evaluation_refs=("eval:parity", "eval:regression"),
    )
    assert proposal.approved
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="no executable parity evidence"):
        registry.apply_migration(proposal)
    assert registry.history == history


def test_forged_and_cross_registry_decisions_do_not_authorize_migration():
    registry, source, target = _registry()
    decision = _decision(registry, source, target)
    other, other_source, other_target = _registry()
    other_decision = _decision(other, other_source, other_target)
    assert other_decision == decision
    for forged in (replace(decision), other_decision):
        with pytest.raises(ModelLifecycleError, match="not issued by this registry"):
            registry.apply_migration(forged)
    assert not registry.migrations


def test_denied_comparison_does_not_mutate_models_and_approval_cannot_be_forged():
    registry, source, target = _registry()
    decision = _decision(registry, source, target, cases=_cases(matches=(True, False, True)))
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="did not pass"):
        registry.apply_migration(decision)
    with pytest.raises(ModelLifecycleError, match="approval must match"):
        replace(decision, approved=True)
    assert registry.history == history and not registry.migrations


@pytest.mark.parametrize("trainer", ("trainer:source", "trainer:target"))
def test_independent_verifier_required_for_evaluation_and_rollback(trainer):
    registry, source, target = _registry()
    with pytest.raises(ModelLifecycleError, match="independent of both trainers"):
        _decision(registry, source, target, verifier_id=trainer)
    migration = registry.apply_migration(_decision(registry, source, target))
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="independent of both trainers"):
        _rollback(registry, migration, verifier_id=trainer)
    assert registry.history == history and not registry.rollbacks


def test_obsolete_evidence_fails_even_when_rollback_restores_same_states():
    registry, source, target = _registry()
    used = _decision(registry, source, target)
    pending = _decision(registry, source, target, evaluation_refs=("eval:second", "eval:third"))
    migration = registry.apply_migration(used)
    _rollback(registry, migration)
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="evidence identity is stale"):
        registry.apply_migration(pending)
    fresh = _decision(registry, source, target)
    assert fresh.decision_digest != used.decision_digest
    assert registry.history == history
    assert registry.apply_migration(fresh).receipt_digest != migration.receipt_digest


def test_pending_migration_cannot_apply_after_model_state_changes():
    registry, source, target = _registry()
    decision = _decision(registry, source, target)
    registry.transition(
        target.model_digest,
        ModelLifecycleState.ACTIVE,
        verifier_id="other-verifier",
        evidence_refs=("canary:other", "rollback:other"),
    )
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="target must be validated"):
        registry.apply_migration(decision)
    assert registry.history == history and not registry.migrations


def test_mbom_license_and_rights_cannot_be_rebound():
    registry, source, target = _registry()
    _decision(registry, source, target)
    for changed in (
        replace(source, rights_refs=("rights:changed",)),
        replace(target, license_refs=("license:changed",)),
    ):
        with pytest.raises(ModelLifecycleError, match="cannot be rebound"):
            registry.register_candidate(changed)


def test_forged_rollback_and_changed_replay_fail_closed():
    registry, source, target = _registry()
    migration = registry.apply_migration(_decision(registry, source, target))
    with pytest.raises(ModelLifecycleError, match="not issued by this registry"):
        _rollback(registry, replace(migration))
    _rollback(registry, migration)
    for overrides in (
        {"verifier_id": "different-verifier"},
        {"evidence_refs": ("incident:other", "restore:other")},
    ):
        with pytest.raises(ModelLifecycleError, match="replay changed"):
            _rollback(registry, migration, **overrides)


@pytest.mark.parametrize(
    "which,state", (("source", ModelLifecycleState.RETIRED), ("target", ModelLifecycleState.DEPRECATED))
)
def test_rollback_cannot_undo_later_lifecycle_actions(which, state):
    registry, source, target = _registry()
    migration = registry.apply_migration(_decision(registry, source, target))
    registry.transition(
        (source if which == "source" else target).model_digest,
        state,
        verifier_id="lifecycle-verifier",
        evidence_refs=("lifecycle:next",),
    )
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="rollback identity is stale"):
        _rollback(registry, migration)
    assert registry.history == history and not registry.rollbacks


def test_normal_transition_cannot_claim_rollback_compensation_authority():
    registry, source, target = _registry()
    registry.apply_migration(_decision(registry, source, target))
    with pytest.raises(ModelLifecycleError, match="illegal lifecycle transition"):
        registry.transition(
            source.model_digest,
            ModelLifecycleState.ACTIVE,
            verifier_id="rollback-verifier",
            evidence_refs=("restore:a", "restore:b"),
        )


def test_history_budget_reserves_compensation_and_failure_is_atomic():
    registry, source, target = _registry(max_transitions=6)
    decision = _decision(registry, source, target)
    history = registry.history
    with pytest.raises(ModelLifecycleError, match="history budget exhausted"):
        registry.apply_migration(decision)
    assert registry.history == history and not registry.migrations
    assert registry.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert registry.state(target.model_digest) is ModelLifecycleState.VALIDATED

    registry, source, target = _registry(max_transitions=7)
    migration = registry.apply_migration(_decision(registry, source, target))
    with pytest.raises(ModelLifecycleError, match="history budget exhausted"):
        registry.transition(
            source.model_digest,
            ModelLifecycleState.RETIRED,
            verifier_id="retirement-verifier",
            evidence_refs=("retire:source",),
        )
    _rollback(registry, migration)
    assert len(registry.history) == 7


def test_inventory_decision_and_case_budgets_are_bounded():
    registry, source, target = _registry(max_models=2, max_decisions=1, max_parity_cases=3)
    with pytest.raises(ModelLifecycleError, match="inventory budget exhausted"):
        registry.register_candidate(_mbom("third"))
    assert registry.register_candidate(source) is source
    with pytest.raises(ModelLifecycleError, match="evaluation budget"):
        _decision(registry, source, target, cases=_cases(matches=(True,) * 4))
    decision = _decision(registry, source, target)
    assert _decision(registry, source, target) is decision
    with pytest.raises(ModelLifecycleError, match="decision budget exhausted"):
        _decision(registry, source, target, evaluation_refs=("eval:other", "eval:second"))


@pytest.mark.parametrize(
    "cases,pattern", (((), "evaluation budget"), ("case", "sequence"), (iter(()), "sequence"))
)
def test_unbounded_or_empty_case_inputs_are_rejected(cases, pattern):
    registry, source, target = _registry()
    with pytest.raises(ModelLifecycleError, match=pattern):
        _decision(registry, source, target, cases=cases)


def test_duplicate_case_and_input_identity_cannot_inflate_parity():
    registry, source, target = _registry()
    cases = _cases()
    with pytest.raises(ModelLifecycleError, match="duplicate parity case"):
        _decision(registry, source, target, cases=(cases[0], cases[0]))
    with pytest.raises(ModelLifecycleError, match="duplicate parity input"):
        _decision(
            registry, source, target, cases=(cases[0], replace(cases[1], input_digest=cases[0].input_digest))
        )


@pytest.mark.parametrize("score", (True, float("nan"), float("inf"), -0.1, 1.1, "1", 10**1000))
def test_invalid_parity_thresholds_fail_without_mutation(score):
    registry, source, target = _registry()
    with pytest.raises(ModelLifecycleError, match="parity scores"):
        _decision(registry, source, target, required_score=score)
    assert not registry.migrations


def test_receipt_constructors_reject_changed_evaluation_and_transition_identity():
    registry, source, target = _registry()
    decision = _decision(registry, source, target)
    evaluation = registry.migration_evaluation(decision)
    with pytest.raises(ModelLifecycleError, match="does not bind"):
        replace(evaluation, evaluation_refs=("eval:changed", "eval:other"))
    with pytest.raises(ModelLifecycleError, match="parity score does not match"):
        replace(evaluation, parity_score=0.5)
    migration = registry.apply_migration(decision)
    with pytest.raises(ModelLifecycleError, match="does not bind"):
        replace(migration, source_lifecycle_digest=_sha("unrelated"))
    with pytest.raises(ModelLifecycleError, match="transition MBOM identity drift"):
        replace(migration, source_mbom_digest=_sha("unrelated"))
    rollback = _rollback(registry, migration)
    with pytest.raises(ModelLifecycleError, match="does not bind"):
        replace(rollback, evidence_refs=("restore:changed", "restore:other"))


def test_concurrent_competing_migrations_authorize_only_one_target():
    registry, source, target = _registry()
    challenger = registry.register_candidate(_mbom("challenger"))
    registry.transition(
        challenger.model_digest,
        ModelLifecycleState.VALIDATED,
        verifier_id="validation-verifier",
        evidence_refs=("eval:quality", "eval:safety"),
    )
    decisions = (_decision(registry, source, target), _decision(registry, source, challenger))
    barrier = Barrier(2)

    def apply(decision):
        barrier.wait(timeout=5)
        try:
            return registry.apply_migration(decision)
        except ModelLifecycleError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(apply, decisions))
    assert sum(isinstance(result, ModelLifecycleError) for result in results) == 1
    assert len(registry.migrations) == 1
    assert (
        sum(registry.state(mbom.model_digest) is ModelLifecycleState.ACTIVE for mbom in (target, challenger))
        == 1
    )
