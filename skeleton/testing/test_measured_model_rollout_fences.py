"""Rollout lease authority must remain live through final publication work."""

import asyncio
from types import SimpleNamespace

import pytest

from skeleton.ai.runtime.learning_foundation import rollout
from skeleton.ai.runtime.learning_foundation.lifecycle import ModelLifecycleRegistry
from skeleton.ai.runtime.learning_foundation.lifecycle_repository import (
    LifecycleSnapshotTransaction,
)
from skeleton.ai.runtime.learning_foundation.rollout import (
    MeasuredModelRollout,
    MeasuredRolloutError,
)
from skeleton.testing.test_measured_local_verifier import _sources
from skeleton.testing.test_measured_model_rollout import _plan, _registry


@pytest.mark.parametrize("operation", ["admission", "append", "completion"])
@pytest.mark.parametrize("publication", ["validation", "save", "memory_validation"])
def test_expiry_during_final_publication_rolls_back_exact_evidence(
    tmp_path, monkeypatch, operation, publication
):
    _, sources = _sources()
    durable = publication != "memory_validation"
    registry = _registry(tmp_path, sources, durable=durable)
    controller = MeasuredModelRollout(registry)
    plan = _plan()
    clock = [1000.0]
    injected = [False]
    monkeypatch.setattr(rollout, "time", SimpleNamespace(time=lambda: clock[0]))

    def selected(snapshot):
        records = snapshot.get("rollouts", [])
        if injected[0] or not records:
            return False
        phase = records[0]["phases"]["shadow"]
        if operation == "admission":
            return phase["owner"] is not None and not phase["cases"]
        if operation == "append":
            return len(phase["cases"]) == 1 and phase["receipt"] is None
        return phase["receipt"] is not None

    if publication == "save":
        original_save = LifecycleSnapshotTransaction.save

        def save(transaction, snapshot):
            result = original_save(transaction, snapshot)
            if selected(snapshot):
                injected[0] = True
                clock[0] += 2
            return result

        monkeypatch.setattr(LifecycleSnapshotTransaction, "save", save)
    else:
        original_validate = ModelLifecycleRegistry._validate_snapshot

        def validate(cls, snapshot):
            result = original_validate(snapshot)
            if selected(snapshot) and (not durable or registry._transaction_depth):
                injected[0] = True
                clock[0] += 2
            return result

        monkeypatch.setattr(ModelLifecycleRegistry, "_validate_snapshot", classmethod(validate))

    def run(target):
        return asyncio.run(
            target.run(
                plan,
                candidate=sources[0],
                baseline=sources[1],
                verifier=sources[2],
                lease_seconds=1,
            )
        )

    with pytest.raises(MeasuredRolloutError, match="expired"):
        run(controller)
    assert injected[0]
    committed_cases = {"admission": 0, "append": 0, "completion": 2}[operation]
    if operation == "admission":
        assert plan.run_id not in registry._rollouts
    else:
        phase = registry._rollouts[plan.run_id]["phases"]["shadow"]
        assert len(phase["cases"]) == committed_cases
        assert phase["receipt"] is None
        assert phase["owner"] is None
    with pytest.raises(MeasuredRolloutError, match="no completed issued receipt"):
        controller.receipt(plan.run_id, "shadow")

    recovered = (
        MeasuredModelRollout(ModelLifecycleRegistry(path=tmp_path / "lifecycle.sqlite3"))
        if durable
        else MeasuredModelRollout(registry)
    )
    prior_calls = len(sources[2].model.calls)
    receipt = run(recovered)
    assert receipt.metrics["sample_count"] == 4
    assert len(sources[2].model.calls) == prior_calls + 2 * (2 - committed_cases)
    assert recovered.receipt(plan.run_id, "shadow") == receipt
