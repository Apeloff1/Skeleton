from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.execution_audit import (
    AuditEventKind,
    ExecutionAuditError,
)
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.types import Goal


def _runtime() -> FrontierJeevesAgentRuntime:
    return FrontierJeevesAgentRuntime(
        provider_router=ProviderRouter([DeterministicProvider([])])
    )


def _inputs(run_id: str = "run-checkpoint-binding") -> RunInputs:
    return RunInputs(
        goal=Goal(
            goal_id="goal-checkpoint-binding",
            objective="Verify checkpoint audit binding.",
        ),
        tenant_id="tenant-checkpoint",
        user_id="user-checkpoint",
        workspace_id="workspace-checkpoint",
        run_id=run_id,
    )


def test_new_frontier_checkpoint_is_reciprocally_bound_before_persistence() -> None:
    runtime = _runtime()
    state = runtime._new_state(_inputs())
    checkpoint = runtime.checkpointer.latest(state.run_id)

    assert checkpoint is not None
    runtime._verify_checkpoint_binding(checkpoint)

    ledger = runtime.runtime_guard.audit_store.get(state.run_id)
    assert ledger is not None
    entries = ledger.entries()
    assert entries
    binding = entries[-1]
    assert binding.kind is AuditEventKind.CHECKPOINT_BOUND
    assert binding.payload["checkpoint_sequence"] == checkpoint.sequence
    assert binding.payload["checkpoint_fingerprint"] == checkpoint.fingerprint
    assert binding.payload["audit_head_before"] == checkpoint.metadata["execution_audit_head"]
    assert binding.payload["audit_events_before"] == checkpoint.metadata["execution_audit_events"]


def test_checkpoint_content_tamper_breaks_reciprocal_binding() -> None:
    runtime = _runtime()
    state = runtime._new_state(_inputs("run-checkpoint-tamper"))
    checkpoint = runtime.checkpointer.latest(state.run_id)
    assert checkpoint is not None

    tampered = replace(
        checkpoint,
        last_error="forged post-persistence checkpoint content",
    )

    assert tampered.fingerprint != checkpoint.fingerprint
    with pytest.raises(ExecutionAuditError, match="not reciprocally bound"):
        runtime._verify_checkpoint_binding(tampered)


def test_checkpoint_audit_prefix_tamper_breaks_binding() -> None:
    runtime = _runtime()
    state = runtime._new_state(_inputs("run-checkpoint-prefix-tamper"))
    checkpoint = runtime.checkpointer.latest(state.run_id)
    assert checkpoint is not None

    metadata = dict(checkpoint.metadata)
    metadata["execution_audit_head"] = "9" * 64
    tampered = replace(checkpoint, metadata=metadata)

    with pytest.raises(ExecutionAuditError, match="not reciprocally bound"):
        runtime._verify_checkpoint_binding(tampered)


def test_missing_audit_binding_rejects_otherwise_valid_checkpoint() -> None:
    runtime = _runtime()
    state = runtime._new_state(_inputs("run-checkpoint-missing-binding"))
    checkpoint = runtime.checkpointer.latest(state.run_id)
    assert checkpoint is not None

    # A different runtime has no execution-audit chain for this checkpoint.
    fresh_runtime = _runtime()
    with pytest.raises(ExecutionAuditError, match="no corresponding execution audit"):
        fresh_runtime._verify_checkpoint_binding(checkpoint)


def test_second_checkpoint_binds_to_prefix_including_prior_binding() -> None:
    runtime = _runtime()
    state = runtime._new_state(_inputs("run-checkpoint-second"))
    first = runtime.checkpointer.latest(state.run_id)
    assert first is not None
    first_ledger = runtime.runtime_guard.audit_store.get(state.run_id)
    assert first_ledger is not None
    event_count_after_first_binding = first_ledger.event_count

    second = runtime._checkpoint(state)

    assert second.sequence == first.sequence + 1
    assert second.metadata["execution_audit_events"] == event_count_after_first_binding
    runtime._verify_checkpoint_binding(second)
    ledger = runtime.runtime_guard.audit_store.get(state.run_id)
    assert ledger is not None
    assert ledger.entries()[-1].payload["checkpoint_fingerprint"] == second.fingerprint