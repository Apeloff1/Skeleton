"""Actual local paired rollout evidence, candidate cutover and durable rollback."""

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest

from skeleton.testing.local_inference_fixtures import local_serving_resources  # noqa: F401

from skeleton.ai.runtime.learning_foundation.lifecycle import (
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)
from skeleton.ai.runtime.learning_foundation.rollout import (
    LocalUsageTariff,
    MeasuredModelRollout,
    MeasuredRolloutError,
    RolloutGatePolicy,
    RolloutPlan,
    _assignment,
)
from skeleton.ai.runtime.training.cli import build_governed_artifact
from skeleton.ai.runtime.training.control import TrainingRepository
from skeleton.ai.runtime.training.data import DatasetRegistry
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer
from skeleton.ai.runtime.training.verifier import (
    EvaluationModelSource,
    canonical,
    digest,
)
from skeleton.testing.test_measured_local_verifier import _sources, _suite


def _registry(tmp_path, sources, *, durable=True):
    registry = (
        ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3") if durable else ModelLifecycleRegistry()
    )
    for source in sources[:2]:
        registry.register_candidate(
            MeasuredModelRollout.mbom_for_source(
                source,
                license_refs=("license:fixture-owned",),
                rights_refs=("rights:local-training-evaluation",),
            )
        )
        registry.transition(
            source.model.model_digest,
            ModelLifecycleState.VALIDATED,
            verifier_id="independent-quality-evaluator",
            evidence_refs=("eval:fixture-heldout", "eval:local-safety"),
        )
    registry.transition(
        sources[1].model.model_digest,
        ModelLifecycleState.ACTIVE,
        verifier_id="independent-baseline-evaluator",
        evidence_refs=("eval:baseline-local", "restore:baseline-local"),
    )
    return registry


def _plan(*, policy=None, run_id="bounded-rollout"):
    # A pinned salt yields both choices in this tiny fixture; no population claim.
    for index in range(100):
        plan = RolloutPlan(
            run_id,
            _suite(),
            canary_basis_points=5000,
            assignment_salt=f"fixture-salt:{index}",
            policy=policy or RolloutGatePolicy(),
        )
        if len({_assignment(plan, "canary", i)["selected_role"] for i in range(2)}) == 2:
            return plan
    raise AssertionError("fixture needs both deterministic canary branches")


def _run(controller, plan, sources, phase="shadow"):
    return asyncio.run(
        controller.run(plan, candidate=sources[0], baseline=sources[1], verifier=sources[2], phase=phase)
    )


def _stage(controller, plan, sources):
    _run(controller, plan, sources)
    measured = _run(controller, plan, sources, "canary")
    return controller.stage(measured, candidate=sources[0], baseline=sources[1], verifier=sources[2])


def _cutover(controller, stage, sources):
    return controller.cutover(stage, candidate=sources[0], baseline=sources[1], verifier=sources[2])


def _rollback(controller, receipt, sources):
    return controller.rollback(
        receipt,
        baseline=sources[1],
        verifier=sources[2],
        evidence_refs=("incident:fixture-regression", "restore:known-baseline"),
    )


def test_actual_shadow_canary_candidate_cutover_restart_and_rollback(tmp_path):
    _, sources = _sources()
    registry = _registry(tmp_path, sources)
    controller = MeasuredModelRollout(registry)
    plan = _plan()
    shadow = _run(controller, plan, sources)
    assert shadow.metrics["selected_candidate_requests"] == 0
    assert shadow.metrics["candidate_accuracy"] == 1
    assert shadow.metrics["baseline_accuracy"] == 0
    for index in range(2):
        request = controller.request_result(plan.run_id, "shadow", index)
        assert request["assignment"] == controller.request_decision(plan.run_id, "shadow", index)
        assert request["assignment"]["selected_role"] == "baseline"
        assert (
            request["measurement"]["candidate"]["answer"]["input_digest"]
            == request["measurement"]["baseline"]["answer"]["input_digest"]
        )
        assert request["measurement"]["candidate"]["judgment"]["decision"] == "accept"
        assert request["measurement"]["baseline"]["judgment"]["decision"] == "reject"
    canary = _run(controller, plan, sources, "canary")
    assert canary.metrics["selected_candidate_requests"] == canary.metrics["selected_baseline_requests"] == 1
    stage = controller.stage(canary, candidate=sources[0], baseline=sources[1], verifier=sources[2])
    assert stage.status == "staged_candidate"
    assert stage.production_routing_authorized is False
    action = _cutover(controller, stage, sources)
    assert action.production_routing_authorized is False
    assert registry.state(sources[0].model.model_digest) is ModelLifecycleState.ACTIVE
    assert registry.state(sources[1].model.model_digest) is ModelLifecycleState.DEPRECATED
    calls = len(sources[2].model.calls)
    reopened = ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3")
    recovered = MeasuredModelRollout(reopened)
    assert _run(recovered, plan, sources, "canary") == canary
    assert len(sources[2].model.calls) == calls
    stage2 = recovered.stage(
        recovered.receipt(plan.run_id, "canary"),
        candidate=sources[0],
        baseline=sources[1],
        verifier=sources[2],
    )
    assert stage2 == stage
    assert _cutover(recovered, stage2, sources) == action
    restored = _rollback(recovered, recovered.action(plan.run_id), sources)
    assert restored.action == "rollback_candidate"
    again = MeasuredModelRollout(ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3"))
    assert _rollback(again, again.action(plan.run_id), sources) == restored
    assert again.registry.state(sources[1].model.model_digest) is ModelLifecycleState.ACTIVE
    assert again.registry.state(sources[0].model.model_digest) is ModelLifecycleState.VALIDATED
    assert len(again.registry.history) == 7


@pytest.mark.parametrize(
    "policy,reason",
    [
        (RolloutGatePolicy(min_output_parity=1), "output_parity_below_threshold"),
        (RolloutGatePolicy(max_total_tokens=0), "actual_usage_budget_exceeded"),
        (RolloutGatePolicy(max_total_cost_units=0), "actual_cost_proxy_budget_exceeded"),
        (RolloutGatePolicy(candidate_tariff=LocalUsageTariff(2, 2)), "candidate_cost_proxy_regressed"),
        (RolloutGatePolicy(max_inference_elapsed_ns=0), "actual_latency_budget_exceeded"),
    ],
)
def test_actual_gate_failures_retain_baseline_and_deny_cutover(tmp_path, policy, reason):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    stage = _stage(controller, _plan(policy=policy), sources)
    assert stage.status == "rejected"
    assert any(reason in value for value in stage.reasons)
    with pytest.raises(MeasuredRolloutError, match="rejected"):
        _cutover(controller, stage, sources)
    assert controller.registry.state(sources[1].model.model_digest) is ModelLifecycleState.ACTIVE
    assert not controller.registry.migrations


def test_unissued_receipt_clones_and_cross_controller_handles_cannot_cutover(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    stage = _stage(controller, plan, sources)
    with pytest.raises(MeasuredRolloutError, match="issued"):
        _cutover(controller, replace(stage), sources)
    other = MeasuredModelRollout(ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3"))
    with pytest.raises(MeasuredRolloutError, match="issued"):
        _cutover(other, stage, sources)
    with pytest.raises(ModelLifecycleError, match="capability"):
        other.registry._rollout_access(lambda registry: registry._rollouts.clear(), _token=object())


def test_pre_cutover_withdrawal_preserves_baseline_and_replay_evidence(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    stage = _stage(controller, plan, sources)
    withdrawal = _rollback(controller, stage, sources)
    assert withdrawal.action == "withdraw_stage"
    assert withdrawal.lifecycle_receipt_digest is None
    assert _rollback(controller, stage, sources) == withdrawal
    with pytest.raises(MeasuredRolloutError, match="withdrawn"):
        _cutover(controller, stage, sources)
    assert controller.registry.state(sources[1].model.model_digest) is ModelLifecycleState.ACTIVE


def test_stale_exact_model_history_blocks_measured_stage(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    _run(controller, plan, sources)
    canary = _run(controller, plan, sources, "canary")
    controller.registry.transition(
        sources[1].model.model_digest,
        ModelLifecycleState.DEPRECATED,
        verifier_id="independent-retirement",
        evidence_refs=("incident:withdraw-candidate",),
    )
    with pytest.raises(MeasuredRolloutError, match="stale"):
        controller.stage(canary, candidate=sources[0], baseline=sources[1], verifier=sources[2])


@pytest.mark.parametrize(
    "override", [{"canary_basis_points": True}, {"canary_basis_points": 10000}, {"seed": True}]
)
def test_rollout_plan_strict_bounds_reject_before_writes(override):
    with pytest.raises((MeasuredRolloutError, RuntimeError)):
        RolloutPlan("bad", _suite(), **override)


def test_plan_binding_cannot_change_after_shadow(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    _run(controller, plan, sources)
    with pytest.raises(MeasuredRolloutError, match="immutable"):
        _run(controller, replace(plan, seed=1), sources, "canary")


@pytest.mark.parametrize("field", ["assignment", "decision", "gold", "metrics", "source", "stage"])
def test_rehashed_durable_rollout_corruption_fails_closed(tmp_path, field):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    _stage(controller, plan, sources)
    repository = controller.registry._repository
    with repository._connection() as db:
        payload = json.loads(db.execute("SELECT payload FROM lifecycle_state").fetchone()[0])
        rollout = payload["rollouts"][0]
        if field == "assignment":
            rollout["phases"]["canary"]["cases"][0]["assignment"]["selected_role"] = "forged"
        elif field == "decision":
            rollout["phases"]["canary"]["decisions"][0]["bucket"] = 10000
        elif field == "gold":
            rollout["phases"]["canary"]["cases"][0]["measurement"]["candidate"]["gold"] = False
        elif field == "metrics":
            receipt = rollout["phases"]["canary"]["receipt"]
            metrics = json.loads(receipt["metrics_json"])
            metrics["candidate_accuracy"] = 0
            receipt["metrics_json"] = canonical(metrics)
        elif field == "source":
            rollout["binding"]["candidate"]["model_digest"] = "b" * 64
        else:
            rollout["stage"]["status"] = "rejected"
        raw = canonical(payload)
        db.execute(
            "UPDATE lifecycle_state SET payload=?,digest=?", (raw, hashlib.sha256(raw.encode()).hexdigest())
        )
    with pytest.raises((ModelLifecycleError, RuntimeError)):
        ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3")


def test_legacy_snapshot_upgrade_and_measured_backup_restore(tmp_path):
    _, sources = _sources()
    registry = _registry(tmp_path, sources)
    assert registry._snapshot()["schema_version"] == 1
    controller = MeasuredModelRollout(registry)
    plan = _plan()
    _run(controller, plan, sources)
    assert registry._snapshot()["schema_version"] == 2
    backup = tmp_path / "backup.sqlite3"
    registry.backup(backup)
    restored, _receipt = ModelLifecycleRegistry.restore_backup(
        backup_path=backup, path=tmp_path / "restored.sqlite3"
    )
    recovered = MeasuredModelRollout(restored)
    calls = len(sources[2].model.calls)
    assert _run(recovered, plan, sources) == controller.receipt(plan.run_id, "shadow")
    assert len(sources[2].model.calls) == calls


def test_actual_native_sources_revocation_denies_cutover_but_restores_baseline(tmp_path):
    sources = []
    resources = []
    for role, word in (("candidate", "right"), ("baseline", "wrong")):
        directory = tmp_path / role
        directory.mkdir()
        corpus = directory / "data.txt"
        corpus.write_text("learned alpha " + word + " fixture learned beta " + word + " fixture")
        build = build_governed_artifact(
            corpus_paths=(corpus,),
            state_directory=directory / "state",
            output_path=directory / "model.json",
            run_id=role,
            dataset_id=role,
            rights_refs=("license:owned",),
            algorithm="reference",
        )
        datasets = DatasetRegistry(directory / "state" / "datasets.sqlite3")
        runs = TrainingRepository(directory / "state" / "training.sqlite3")
        sources.append(EvaluationModelSource.from_training(ReferenceLocalTrainer(datasets, runs), role))
        resources.append((datasets, runs, build))
    _, legacy = _sources()
    sources.append(legacy[2])
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    stage = _stage(controller, plan, sources)
    assert stage.status == "staged_candidate"
    action = _cutover(controller, stage, sources)
    datasets, _runs, build = resources[0]
    envelope = datasets.materialized_sources(build["dataset_digest"])[0].envelope
    datasets.revoke_source_rights(
        envelope.content_digest, reason="candidate rights revoked", command_id="fixture-revoke"
    )
    with pytest.raises(PermissionError, match="revoked"):
        _cutover(controller, stage, sources)
    restored = _rollback(controller, action, sources)
    assert restored.action == "rollback_candidate"
    assert controller.registry.state(sources[1].model.model_digest) is ModelLifecycleState.ACTIVE
    for datasets, runs, _ in resources:
        runs.close()
        datasets.close()


def test_committed_case_prefix_survives_write_failure_and_restart(tmp_path, monkeypatch):
    from skeleton.ai.runtime.learning_foundation.lifecycle_repository import (
        LifecycleSnapshotTransaction,
    )

    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    original = LifecycleSnapshotTransaction.save
    injected = [False]

    def save(self, snapshot):
        records = snapshot.get("rollouts", [])
        if records and len(records[0]["phases"]["shadow"]["cases"]) == 2 and not injected[0]:
            injected[0] = True
            raise OSError("injected durable case write failure")
        return original(self, snapshot)

    monkeypatch.setattr(LifecycleSnapshotTransaction, "save", save)
    with pytest.raises(OSError, match="write failure"):
        _run(controller, plan, sources)
    assert len(sources[2].model.calls) == 4
    assert len(controller.registry._rollouts[plan.run_id]["phases"]["shadow"]["cases"]) == 1
    reopened = MeasuredModelRollout(ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3"))
    receipt = _run(reopened, plan, sources)
    assert receipt.metrics["sample_count"] == 4
    assert len(sources[2].model.calls) == 6
    assert sum(value["task"] == "alpha" for value in sources[2].model.calls) == 2


def test_cutover_write_failure_does_not_publish_action_or_change_model_states(tmp_path, monkeypatch):
    from skeleton.ai.runtime.learning_foundation.lifecycle_repository import (
        LifecycleSnapshotTransaction,
    )

    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    stage = _stage(controller, plan, sources)
    original = LifecycleSnapshotTransaction.save

    def fail_cutover(self, snapshot):
        if snapshot.get("rollouts") and snapshot["rollouts"][0]["cutover"] is not None:
            raise OSError("cutover commit failed")
        return original(self, snapshot)

    with monkeypatch.context() as context:
        context.setattr(LifecycleSnapshotTransaction, "save", fail_cutover)
        with pytest.raises(OSError, match="commit failed"):
            _cutover(controller, stage, sources)
    assert not controller.registry.migrations
    assert controller.registry.state(sources[1].model.model_digest) is ModelLifecycleState.ACTIVE
    with pytest.raises(MeasuredRolloutError, match="unavailable"):
        controller.action(plan.run_id)
    action = _cutover(controller, stage, sources)
    assert action.action == "cutover_candidate"


def test_active_epoch_blocks_second_connection_and_expiry_fences_private_append(tmp_path, monkeypatch):
    from skeleton.ai.runtime.learning_foundation.lifecycle_repository import (
        LifecycleSnapshotTransaction,
    )

    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    original = LifecycleSnapshotTransaction.save

    def fail_second(self, snapshot):
        if snapshot.get("rollouts") and len(snapshot["rollouts"][0]["phases"]["shadow"]["cases"]) == 2:
            raise OSError("pause pending run")
        return original(self, snapshot)

    with monkeypatch.context() as context:
        context.setattr(LifecycleSnapshotTransaction, "save", fail_second)
        with pytest.raises(OSError):
            _run(controller, plan, sources)

    def lease(registry):
        state = registry._rollouts[plan.run_id]["phases"]["shadow"]
        state.update(owner="surviving-worker", epoch=state["epoch"] + 1, expires=10**12)
        return state["epoch"]

    epoch = controller._access(lease)
    other = MeasuredModelRollout(ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3"))
    with pytest.raises(MeasuredRolloutError, match="active worker"):
        _run(other, plan, sources)

    def expire(registry):
        registry._rollouts[plan.run_id]["phases"]["shadow"]["expires"] = 1.0

    controller._access(expire)

    def stale(registry):
        controller._owned(registry._rollouts[plan.run_id], "shadow", "surviving-worker", epoch)

    with pytest.raises(MeasuredRolloutError, match="expired"):
        controller._access(stale)
    assert _run(other, plan, sources).metrics["sample_count"] == 4


def test_run_scoped_memory_registry_rollout_retains_default_api(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources, durable=False))
    plan = _plan()
    stage = _stage(controller, plan, sources)
    action = _cutover(controller, stage, sources)
    assert _rollback(controller, action, sources).action == "rollback_candidate"
    assert controller.registry.durable is False


def test_declared_rights_scope_denied_before_rollout_creation(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan(policy=RolloutGatePolicy(required_rights_refs=("rights:undeclared-external-transfer",)))
    with pytest.raises(MeasuredRolloutError, match="rights"):
        _run(controller, plan, sources)
    assert not controller.registry._rollouts
    assert controller.registry._snapshot()["schema_version"] == 1
    assert sources[2].model.calls == []


def test_canary_requires_both_assignment_branches_before_staging(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    for index in range(100):
        plan = RolloutPlan(
            "single-choice", _suite(), canary_basis_points=1, assignment_salt=f"no-canary-choice:{index}"
        )
        if all(_assignment(plan, "canary", case)["selected_role"] == "baseline" for case in range(2)):
            break
    stage = _stage(controller, plan, sources)
    assert stage.status == "rejected"
    assert "canary:assignment_coverage_insufficient" in stage.reasons


def test_paired_baseline_input_seed_cannot_be_rewritten(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    _run(controller, plan, sources)
    with controller.registry._repository._connection() as db:
        snapshot = json.loads(db.execute("SELECT payload FROM lifecycle_state").fetchone()[0])
        observation = snapshot["rollouts"][0]["phases"]["shadow"]["cases"][0]
        observation["measurement"]["baseline"]["answer"]["input_digest"] = digest(
            {"prompt": "alpha", "max_output_tokens": 1, "seed": plan.seed + 1}
        )
        raw = canonical(snapshot)
        db.execute(
            "UPDATE lifecycle_state SET payload=?,digest=?", (raw, hashlib.sha256(raw.encode()).hexdigest())
        )
    with pytest.raises((ModelLifecycleError, RuntimeError)):
        ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3")


def test_nonempty_inference_epoch_is_required_for_complete_phase(tmp_path):
    _, sources = _sources()
    controller = MeasuredModelRollout(_registry(tmp_path, sources))
    plan = _plan()
    _run(controller, plan, sources)
    with controller.registry._repository._connection() as db:
        snapshot = json.loads(db.execute("SELECT payload FROM lifecycle_state").fetchone()[0])
        snapshot["rollouts"][0]["phases"]["shadow"]["epoch"] = 0
        raw = canonical(snapshot)
        db.execute(
            "UPDATE lifecycle_state SET payload=?,digest=?", (raw, hashlib.sha256(raw.encode()).hexdigest())
        )
    with pytest.raises(MeasuredRolloutError, match="unstarted"):
        ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3")
