"""No-autoretry Jeeves cold recovery on the canonical SQLite authority.

A held canonical cross-process SessionGate protects the entire planner run,
not just each individual model call. The restart path verifies exact owner,
model, task, budgets and every checkpoint chain entry. Only reasoning-only
incomplete checkpoints may resume. A tool step in-flight, a terminal checkpoint
or an uncertain native call never receives an automatic second effect.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from .native_checkpoint_journal import NativeCheckpointHold, NativeSQLiteCheckpointer
from .native_run_memory import run_memory_manager, NativeRunMemoryStore
from .types import MemoryKind
from .native_runtime import NativeJeevesRuntime
from .strict_runtime import StrictJeevesAgentRuntime
from .runtime import RunInputs
from .types import AgentPhase, StepStatus


class NativeDurableAgentHold(NativeCheckpointHold):
    """A restart attempt cannot safely continue this Jeeves run."""


class _JournaledStrictNativeAgent(StrictJeevesAgentRuntime):
    """Fence native inference BEFORE calling the canonical GGUF provider."""

    def _remember_working(
        self, namespace, content, *, kind=MemoryKind.WORKING,
        source, tags, trust, salience, evidence=(),
    ):
        # The ordinary runtime swallows optional memory errors. This durable
        # lane must not silently continue with a divergent, unpersisted context.
        self.memory.remember(
            namespace, content, kind=kind, salience=salience, trust=trust,
            source=source, evidence=evidence, tags=tags,
            ttl_seconds=self.config.working_memory_ttl_seconds,
            metadata={"automatic": True, "promoted": False},
        )

    def _model_call(self, state, **kwargs):
        self.checkpointer.begin_native_call(state.run_id, state.checkpoint_sequence)
        # A raised exception leaves the intent held. The surrounding Jeeves
        # failure checkpoint cannot silently convert uncertainty into replay.
        response = super()._model_call(state, **kwargs)
        self.checkpointer.complete_native_call(state.run_id)
        return response

    def _finalize(self, state):
        result = super()._finalize(state)
        if result.success:
            self.checkpointer.write_terminal_result(result)
        return result

    def _finish_failure(self, state, reason, answer, **kwargs):
        result = super()._finish_failure(state, reason, answer, **kwargs)
        self.checkpointer.write_terminal_result(result)
        return result


class NativeDurableJeevesAgent:
    """Durable reasoning lane; read-only source tools remain a separate lane.

    In particular, grants and confirmed actions are never reconstituted after
    a restart, and no network or filesystem mutation tool is registered here.
    """

    def __init__(self, worker: Any) -> None:
        self.worker = worker
        self.identity = ActiveModel.from_supervisor(worker)
        self.checkpoints = NativeSQLiteCheckpointer(worker)
        self._active_run_id = None
        self.agent = NativeJeevesRuntime(
            worker, checkpointer=self.checkpoints,
            runtime_type=_JournaledStrictNativeAgent,
        )

    def _admit(self, inputs: RunInputs) -> None:
        if not isinstance(inputs, RunInputs) or inputs.run_id is None:
            raise NativeDurableAgentHold("explicit typed run_id is mandatory")
        if inputs.grants or inputs.confirmed_actions:
            raise NativeDurableAgentHold("durable agent does not restore ephemeral tools")
        if (inputs.tenant_id != self.identity.tenant
                or inputs.user_id != self.identity.subject
                or inputs.preferred_provider != "jeeves_native"):
            raise NativeDurableAgentHold("native-only durable principal required")
        if ActiveModel.from_supervisor(self.worker) != self.identity:
            raise NativeDurableAgentHold("active native model identity changed")

    def _gate(self, run_id: str):
        # Stable hashed name cannot collide with native session identifiers.
        # The gate is held for entire agent.run/resume, including model calls.
        gate_name = "jeeves_" + sha256(run_id.encode("utf-8")).hexdigest()[:48]
        return self.worker.spine.session_gate.hold(gate_name, deadline_ms=30000)

    def _bind_memory(self, inputs: RunInputs) -> None:
        # One durable instance owns one run. Do not allow a concurrent caller
        # to replace another run's memory manager in the same runtime object.
        if self._active_run_id not in (None, inputs.run_id):
            raise NativeDurableAgentHold("runtime already owns another durable run")
        self.agent.agent.memory = run_memory_manager(self.checkpoints, inputs)
        self._active_run_id = inputs.run_id

    def run(self, inputs: RunInputs):
        self._admit(inputs)
        with self._gate(inputs.run_id):
            self.checkpoints.create_run(inputs)
            self._bind_memory(inputs)
            return self.agent.run(inputs)

    def resume_operator_approved(self, inputs: RunInputs):
        """Explicit operator call, never triggered automatically on startup."""
        self._admit(inputs)
        with self._gate(inputs.run_id):
            self.checkpoints.bind_existing(inputs)
            self._bind_memory(inputs)
            self.checkpoints.assert_no_inflight(inputs.run_id)
            checkpoint = self.checkpoints.latest(inputs.run_id)
            if checkpoint is None:
                raise NativeDurableAgentHold("no checkpoint; inspect admission before recovery")
            if checkpoint.phase in (
                AgentPhase.COMPLETED, AgentPhase.FAILED, AgentPhase.CANCELLED,
            ):
                raise NativeDurableAgentHold("terminal run cannot regenerate native inference")
            if checkpoint.usage.tool_calls:
                raise NativeDurableAgentHold("tool history requires separate audited reconciliation")
            if checkpoint.plan is not None:
                if any(step.tool is not None for step in checkpoint.plan.steps):
                    raise NativeDurableAgentHold("tool-capable plan cannot be automatically resumed")
                if any(step.status is StepStatus.RUNNING for step in checkpoint.plan.steps):
                    raise NativeDurableAgentHold("in-flight step requires explicit investigation")
            if checkpoint.phase not in (
                AgentPhase.CREATED, AgentPhase.PLANNING,
                AgentPhase.EXECUTING, AgentPhase.VERIFYING,
                AgentPhase.REPLANNING, AgentPhase.FINALIZING,
            ):
                raise NativeDurableAgentHold("unrecognized recovery phase")
            # ModelRequest IDs are deterministic. If a generation committed
            # before a checkpoint crashed, NativeJeevesProvider replays that
            # exact SQLite result. If pending/unknown, the spine denies it.
            return self.agent.resume_in_process(inputs, inputs.run_id)

    def replay_terminal(self, inputs: RunInputs) -> dict[str, object]:
        """Return a previously sealed answer without any native generation."""
        self._admit(inputs)
        with self._gate(inputs.run_id):
            self.checkpoints.bind_existing(inputs)
            sealed = self.checkpoints.terminal_result(inputs.run_id)
            if sealed is None:
                raise NativeDurableAgentHold("no committed terminal answer to replay")
            return {**sealed, "replayed": True}

    def inspect(self, inputs: RunInputs) -> dict[str, object]:
        self._admit(inputs)
        with self._gate(inputs.run_id):
            self.checkpoints.bind_existing(inputs)
            memories = NativeRunMemoryStore(self.checkpoints, inputs)
            record = self.checkpoints.inspect(inputs.run_id)
            checkpoint = self.checkpoints.latest(inputs.run_id)
            safe = bool(checkpoint is not None and
                checkpoint.phase not in (AgentPhase.FAILED, AgentPhase.COMPLETED, AgentPhase.CANCELLED)
                and checkpoint.usage.tool_calls == 0 and
                not self.checkpoints.has_inflight(inputs.run_id) and
                (checkpoint.plan is None or all(
                    step.tool is None and step.status is not StepStatus.RUNNING
                    for step in checkpoint.plan.steps
                )))
            return {**record, "durable_working_memory_records": memories.persisted_records,
                    "operator_resume_structurally_admissible": safe,
                    "native_pending_reservation_clear": "unverified",
                    "automatic_resume": False}


__all__ = ["NativeDurableAgentHold", "NativeDurableJeevesAgent"]
