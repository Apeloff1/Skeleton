from __future__ import annotations

import pytest

from skeleton.storage.cas import (
    DurableSagaStateStore,
    StorageContractError,
    TransactionMode,
    TransactionPlan,
)


def test_transaction_strategy_is_explicit_and_bounded() -> None:
    plan = TransactionPlan(
        operation_id="op-123",
        tenant_id="tenant-a",
        mode=TransactionMode.SAGA,
        resources=("model-registry", "artifact-store", "model-registry"),
        rationale="cross-resource activation needs compensating rollback",
    )

    assert plan.mode is TransactionMode.SAGA
    assert plan.resources == ("model-registry", "artifact-store")


def test_effect_cannot_apply_before_compensation_is_durable() -> None:
    store = DurableSagaStateStore()
    store.begin(
        saga_id="saga-1",
        tenant_id="tenant-a",
        operation_id="op-1",
    )

    with pytest.raises(StorageContractError, match="prepared before effect"):
        store.mark_effect_applied(
            saga_id="saga-1",
            index=0,
            effect_receipt="effect:1",
        )


def test_saga_compensation_state_survives_process_reopen(tmp_path) -> None:
    path = tmp_path / "sagas.sqlite"
    first = DurableSagaStateStore(str(path))
    first.begin(
        saga_id="saga-2",
        tenant_id="tenant-a",
        operation_id="op-2",
    )
    first.prepare_step(
        saga_id="saga-2",
        index=0,
        name="publish-model",
        compensation_ref="model-registry:deactivate",
        compensation_payload={"model_id": "model-7"},
    )
    first.mark_effect_applied(
        saga_id="saga-2",
        index=0,
        effect_receipt="registry-write:abc",
    )

    reopened = DurableSagaStateStore(str(path))
    snapshot = reopened.snapshot(saga_id="saga-2")
    assert snapshot.state == "open"
    assert len(snapshot.steps) == 1
    assert snapshot.steps[0].state == "applied"
    assert snapshot.steps[0].compensation_ref == "model-registry:deactivate"
    assert snapshot.steps[0].effect_receipt == "registry-write:abc"

    reopened.begin_compensation(saga_id="saga-2")
    reopened.mark_compensated(saga_id="saga-2", index=0)
    reopened.finish(saga_id="saga-2", state="compensated")
    final = reopened.snapshot(saga_id="saga-2")
    assert final.state == "compensated"
    assert final.steps[0].state == "compensated"


def test_completed_saga_requires_all_prepared_steps_applied() -> None:
    store = DurableSagaStateStore()
    store.begin(
        saga_id="saga-3",
        tenant_id="tenant-a",
        operation_id="op-3",
    )
    store.prepare_step(
        saga_id="saga-3",
        index=0,
        name="external-write",
        compensation_ref="external:undo",
        compensation_payload=b"undo-token",
    )

    with pytest.raises(StorageContractError, match="every prepared step"):
        store.finish(saga_id="saga-3", state="completed")



def test_compensation_requires_saga_compensating_phase() -> None:
    store = DurableSagaStateStore()
    store.begin(
        saga_id="saga-4",
        tenant_id="tenant-a",
        operation_id="op-4",
    )
    store.prepare_step(
        saga_id="saga-4",
        index=0,
        name="publish",
        compensation_ref="publish:undo",
        compensation_payload=b"token",
    )
    store.mark_effect_applied(
        saga_id="saga-4",
        index=0,
        effect_receipt="effect:4",
    )

    with pytest.raises(StorageContractError, match="while saga is compensating"):
        store.mark_compensated(saga_id="saga-4", index=0)

    store.begin_compensation(saga_id="saga-4")
    with pytest.raises(StorageContractError, match="while saga is open"):
        store.mark_effect_applied(
            saga_id="saga-4",
            index=0,
            effect_receipt="effect:4b",
        )


def test_terminal_saga_transitions_fail_closed() -> None:
    store = DurableSagaStateStore()
    store.begin(
        saga_id="saga-5",
        tenant_id="tenant-a",
        operation_id="op-5",
    )
    store.prepare_step(
        saga_id="saga-5",
        index=0,
        name="write",
        compensation_ref="write:undo",
        compensation_payload=b"undo",
    )
    store.mark_effect_applied(
        saga_id="saga-5",
        index=0,
        effect_receipt="effect:5",
    )
    store.finish(saga_id="saga-5", state="completed")

    with pytest.raises(StorageContractError, match="cannot transition"):
        store.finish(saga_id="saga-5", state="failed")
    with pytest.raises(StorageContractError, match="cannot enter compensation"):
        store.begin_compensation(saga_id="saga-5")
