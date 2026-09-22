"""Strict Jeeves runtime with mandatory epistemic tool enforcement.

``JeevesAgentRuntime`` predates the epistemic authorization stack and therefore
calls ``ToolExecutor`` directly after the original host policy check. This
subclass closes that route for the public hardened runtime without rewriting the
mature planning/finalization machinery.

Only tool-step execution and checkpoint restoration are specialized here. All
other behavior remains inherited from the evidence-first runtime.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable

from .execution_audit import (
    AuditEventKind,
    AuditSeverity,
    InMemoryExecutionAuditStore,
)
from .model_based_control import LearnedTransitionModel, TransitionOutcome
from .policy import PolicyContext
from .runtime import (
    JeevesAgentRuntime as BaseJeevesAgentRuntime,
    RunCheckpoint,
    _RunState,
)
from .runtime_guard import (
    RuntimeEpistemicGuard,
    RuntimeGuardDenied,
    RuntimeGuardPolicy,
    RuntimeGuardRequest,
    RuntimeGuardSignals,
)
from .tools import ToolExecutionContext
from .types import (
    AgentPhase,
    AgentResult,
    Decision,
    StepStatus,
    TerminationReason,
    ToolCall,
    stable_fingerprint,
    stable_id,
)
from .verification import StepVerifier
from .world_model import BeliefGraph


class StrictJeevesAgentRuntime(BaseJeevesAgentRuntime):
    """Evidence-first runtime whose normal tool path cannot bypass the guard."""

    def __init__(
        self,
        *,
        runtime_guard: RuntimeEpistemicGuard | None = None,
        runtime_guard_policy: RuntimeGuardPolicy | None = None,
        guard_world: BeliefGraph | None = None,
        guard_transition_model: LearnedTransitionModel | None = None,
        guard_audit_store: InMemoryExecutionAuditStore | None = None,
        wall_clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        super().__init__(wall_clock=wall_clock, **kwargs)
        if runtime_guard is not None and any(
            value is not None
            for value in (
                runtime_guard_policy,
                guard_world,
                guard_transition_model,
                guard_audit_store,
            )
        ):
            raise ValueError(
                "runtime_guard cannot be combined with guard component overrides"
            )
        self.runtime_guard = runtime_guard or RuntimeEpistemicGuard(
            self.tool_executor,
            policy=runtime_guard_policy,
            world=guard_world,
            transition_model=guard_transition_model,
            audit_store=guard_audit_store,
            wall_clock=wall_clock,
        )

    def _execute_tool_step(self, state: _RunState, step) -> AgentResult | None:
        registered = self.tools.get(step.tool or "")
        if registered is None:
            assert state.plan is not None
            state.plan = self.scheduler.fail(state.plan, step.step_id, retryable=False)
            state.last_error = f"tool unavailable: {step.tool}"
            return self._handle_step_failure(state, step, None, tool_failed=True)

        policy_context = PolicyContext(
            run_id=state.run_id,
            user_id=state.inputs.user_id,
            goal=state.inputs.goal,
            usage=state.usage,
            budget=state.inputs.budget,
            started_at=state.started_monotonic,
            confirmed_actions=state.inputs.confirmed_actions,
            metadata=state.inputs.metadata,
        )
        host_decision = self.execution_policy.check_tool(
            policy_context,
            registered.spec,
            step.arguments,
            state.inputs.grants,
        )
        state.trace.emit(
            "tool.policy",
            {
                "step_id": step.step_id,
                "tool": step.tool,
                "decision": host_decision.decision.value,
                "reason": host_decision.reason,
                "confirmation_id": host_decision.required_confirmation_id,
                "epistemic_guard_required": True,
            },
        )
        if host_decision.decision is Decision.REQUIRE_CONFIRMATION:
            return self._finish_failure(
                state,
                TerminationReason.CONFIRMATION_REQUIRED,
                host_decision.reason,
                metadata={
                    "confirmation_id": host_decision.required_confirmation_id,
                    "epistemic_guard": "not_reached",
                },
                terminal_phase=AgentPhase.FAILED,
            )
        if host_decision.decision is not Decision.ALLOW:
            assert state.plan is not None
            state.plan = self.scheduler.fail(state.plan, step.step_id, retryable=False)
            return self._finish_failure(
                state,
                TerminationReason.POLICY_DENIED,
                host_decision.reason,
                metadata={
                    "tool": step.tool,
                    "step_id": step.step_id,
                    "epistemic_guard": "not_reached",
                },
            )

        self._raise_if_tool_budget_exhausted(state)
        call = ToolCall(
            call_id=stable_id(
                "call",
                {
                    "run": state.run_id,
                    "step": step.step_id,
                    "attempt": step.attempts,
                    "tool": step.tool,
                    "arguments": step.arguments,
                },
            ),
            name=step.tool or "",
            arguments=step.arguments,
            reason=step.description,
        )
        execution_context = ToolExecutionContext(
            run_id=state.run_id,
            user_id=state.inputs.user_id,
            trace_id=state.trace.trace_id,
            metadata={
                "goal_id": state.inputs.goal.goal_id,
                "step_id": step.step_id,
                "strict_runtime": True,
            },
        )
        guard_request = RuntimeGuardRequest(
            run_id=state.run_id,
            goal_id=state.inputs.goal.goal_id,
            step_id=step.step_id,
            attempt=step.attempts,
            plan_version=state.plan.version if state.plan is not None else 0,
            call=call,
            execution_context=execution_context,
            tool_spec=registered.spec,
            grants=tuple(state.inputs.grants),
            host_policy_decision=host_decision,
            confirmed_actions=state.inputs.confirmed_actions,
            usage=state.usage,
            budget=state.inputs.budget,
            signals=self._runtime_guard_signals(state),
            evidence_ids=tuple(
                artifact.evidence_id for artifact in state.ledger.artifacts()
            ),
            metadata={
                "tenant_id": state.inputs.tenant_id,
                "workspace_id": state.inputs.workspace_id,
                "session_id": state.inputs.session_id,
            },
        )
        try:
            with state.tracer.span(
                "agent.tool.guarded",
                tool=call.name,
                step_id=step.step_id,
            ):
                guarded = self.runtime_guard.execute(guard_request)
        except RuntimeGuardDenied as exc:
            assert state.plan is not None
            state.plan = self.scheduler.fail(state.plan, step.step_id, retryable=False)
            state.last_error = str(exc)[:8192]
            state.trace.emit(
                "tool.epistemic_denied",
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "operation_id": exc.operation_id,
                    "decision_id": exc.decision_id,
                    "disposition": exc.disposition.value if exc.disposition else None,
                    "reason": str(exc),
                },
            )
            self.metrics.increment("agent.tools.epistemic_denied")
            self._checkpoint(state)
            return self._finish_failure(
                state,
                TerminationReason.POLICY_DENIED,
                "Epistemic runtime guard denied the tool call.",
                metadata={
                    "tool": step.tool,
                    "step_id": step.step_id,
                    "operation_id": exc.operation_id,
                    "decision_id": exc.decision_id,
                    "epistemic_disposition": exc.disposition.value
                    if exc.disposition
                    else None,
                },
            )

        observation = guarded.observation
        state.usage = state.usage.add(tool_calls=1)
        state.observations.append(observation)
        state.trace.emit(
            "tool.epistemic_authorized",
            {
                "step_id": step.step_id,
                "tool": call.name,
                "operation_id": guarded.operation_id,
                "decision_id": guarded.decision.decision_id,
                "decision_fingerprint": guarded.decision.fingerprint,
                "admission_mode": guarded.admission_mode.value,
                "prediction_observations": guarded.prediction.observations,
                "prediction_uncertainty": guarded.prediction.uncertainty,
                "audit_head": guarded.audit_head_after_observation,
            },
        )
        state.trace.emit(
            "tool.observed",
            {
                "call_id": call.call_id,
                "tool": call.name,
                "ok": observation.ok,
                "cached": observation.cached,
                "latency_ms": observation.latency_ms,
                "evidence_ids": [ref.evidence_id for ref in observation.evidence],
                "guard_operation_id": guarded.operation_id,
            },
        )
        artifacts = state.ledger.ingest_observation(observation)
        self._bridge_artifacts(state, artifacts)
        self._checkpoint(state)

        self._transition(state, AgentPhase.VERIFYING)
        advisory = self._verification_advisory(state, step, observation)
        verifier = StepVerifier(
            state.ledger,
            policy=self.verification_policy,
            clock=self._wall_clock,
        )
        report = verifier.verify(
            step,
            observations=(observation,),
            advisory=advisory,
        )
        state.last_verification = report
        outcome = (
            TransitionOutcome.SUCCESS
            if observation.ok and report.passed
            else TransitionOutcome.FAILURE
        )
        evidence_ids = tuple(artifact.evidence_id for artifact in artifacts)
        evidence_fingerprint = stable_fingerprint(
            [
                (
                    artifact.evidence_id,
                    artifact.fingerprint,
                    artifact.kind.value,
                    artifact.source,
                )
                for artifact in artifacts
            ]
        )
        try:
            finalization = self.runtime_guard.finalize(
                guarded,
                verification_score=report.score,
                outcome=outcome,
                evidence_ids=evidence_ids,
                evidence_fingerprint=evidence_fingerprint,
                signals=self._runtime_guard_signals(
                    state,
                    anticipated_success=report.passed,
                ),
            )
        except Exception as exc:
            state.last_error = (
                "runtime guard finalization failed: "
                f"{type(exc).__name__}: {str(exc)[:2048]}"
            )
            state.trace.emit(
                "tool.guard_finalization_failed",
                {
                    "step_id": step.step_id,
                    "operation_id": guarded.operation_id,
                    "error": state.last_error,
                },
            )
            self.metrics.increment("agent.tools.guard_finalization_failed")
            return self._finish_failure(
                state,
                TerminationReason.INTERNAL_ERROR,
                "Tool result could not be safely committed to the epistemic audit chain.",
                metadata={
                    "tool": step.tool,
                    "step_id": step.step_id,
                    "operation_id": guarded.operation_id,
                },
            )

        state.trace.emit(
            "tool.guard_finalized",
            {
                "step_id": step.step_id,
                "operation_id": finalization.operation_id,
                "experience_id": finalization.experience.experience_id,
                "outcome": finalization.outcome.value,
                "verification_score": finalization.verification_score,
                "model_fingerprint": finalization.model_fingerprint,
                "audit_head": finalization.audit_checkpoint.head_hash,
                "audit_events": finalization.audit_checkpoint.event_count,
            },
        )
        self.metrics.increment("agent.tools.epistemic_finalized")

        if report.passed:
            assert state.plan is not None
            state.plan = self.scheduler.succeed(state.plan, step.step_id)
            state.trace.emit("step.succeeded", self._verification_event(report))
            self.metrics.increment("agent.steps.succeeded")
            self._checkpoint(state)
            return None

        assert state.plan is not None
        retryable = (
            observation.ok
            and step.attempts < step.max_attempts
            and not report.fatal
        )
        state.plan = self.scheduler.fail(
            state.plan,
            step.step_id,
            retryable=retryable,
        )
        state.trace.emit(
            "step.verification_failed",
            self._verification_event(report),
        )
        self.metrics.increment("agent.steps.verification_failed")
        self._checkpoint(state)
        if retryable:
            return None
        return self._handle_step_failure(
            state,
            step,
            report,
            tool_failed=not observation.ok,
        )

    def _state_from_checkpoint(
        self,
        inputs,
        checkpoint: RunCheckpoint,
    ) -> _RunState:
        audit_head = str(
            checkpoint.metadata.get("execution_audit_head", "0" * 64)
        )
        audit_events = int(
            checkpoint.metadata.get("execution_audit_events", 0)
        )
        self.runtime_guard.note_resume(
            checkpoint.run_id,
            checkpoint_sequence=checkpoint.sequence,
            expected_audit_head=audit_head,
            expected_audit_events=audit_events,
        )
        self.runtime_guard.authorizer.revoke_all(
            reason="runtime resume invalidated outstanding authorization"
        )
        self._close_orphaned_guard_operations(checkpoint.run_id)
        return super()._state_from_checkpoint(inputs, checkpoint)

    def _close_orphaned_guard_operations(self, run_id: str) -> None:
        report = self.runtime_guard.verify_audit(
            run_id,
            require_finalized_operations=False,
        )
        ledger = self.runtime_guard.audit_store.get_or_create(run_id)
        for operation in report.operations:
            if operation.finalized or operation.terminal_kind is not None:
                continue
            ledger.append(
                AuditEventKind.EXECUTION_FAILED,
                {
                    "reason": "runtime resumed before guarded operation finalized",
                    "recovery": True,
                    "event_ids": list(operation.event_ids),
                    "intent_fingerprint": operation.intent_fingerprint,
                    "decision_id": operation.decision_id,
                    "token_id": operation.token_id,
                    "permit_id": operation.permit_id,
                    "call_id": operation.call_id,
                    "observation_fingerprint": operation.observation_fingerprint,
                    "experience_id": operation.experience_id,
                },
                operation_id=operation.operation_id,
                severity=AuditSeverity.WARNING,
            )
            self.metrics.increment("agent.tools.guard_orphans_closed")

    def _checkpoint(self, state: _RunState) -> RunCheckpoint:
        """Save the base checkpoint with the current audit root bound into metadata."""

        audit = self.runtime_guard.audit_checkpoint(state.run_id)
        state.checkpoint_sequence += 1
        scratch = {
            entry.key: {
                "value": entry.value,
                "importance": entry.importance,
            }
            for entry in state.scratch.entries()
        }
        checkpoint = RunCheckpoint(
            run_id=state.run_id,
            goal_id=state.inputs.goal.goal_id,
            phase=state.phase,
            sequence=state.checkpoint_sequence,
            usage=state.usage,
            plan=state.plan,
            observations=tuple(state.observations),
            evidence=state.ledger.artifacts(),
            scratch=scratch,
            replan_count=state.replan_count,
            previous_trace_fingerprint=state.previous_trace_fingerprint,
            current_trace_fingerprint=state.trace.fingerprint,
            last_error=state.last_error,
            created_at=state.created_wall,
            updated_at=self._wall_clock(),
            metadata={
                "tenant_id": state.inputs.tenant_id,
                "user_id": state.inputs.user_id,
                "workspace_id": state.inputs.workspace_id,
                "session_id": state.inputs.session_id,
                "evidence_fingerprint": state.ledger.fingerprint,
                "strict_runtime": True,
                "runtime_guard_policy": self.runtime_guard.policy.fingerprint,
                "execution_audit_head": audit.head_hash,
                "execution_audit_events": audit.event_count,
                "execution_audit_checkpoint": audit.checkpoint_fingerprint,
                "transition_model_fingerprint": self.runtime_guard.transition_model.fingerprint,
                "world_model_fingerprint": self.runtime_guard.world.snapshot(
                    persist=False
                ).fingerprint,
            },
        )
        self.checkpointer.save(checkpoint)
        self.metrics.increment("agent.checkpoints.saved")
        return checkpoint

    def audit_report(
        self,
        run_id: str,
        *,
        require_finalized_operations: bool = True,
    ):
        return self.runtime_guard.verify_audit(
            run_id,
            require_finalized_operations=require_finalized_operations,
        )

    def _runtime_guard_signals(
        self,
        state: _RunState,
        *,
        anticipated_success: bool | None = None,
    ) -> RuntimeGuardSignals:
        plan = state.plan
        total_steps = len(plan.steps) if plan is not None else 1
        completed = 0
        failures = 0
        if plan is not None:
            for item in plan.steps:
                if item.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}:
                    completed += 1
                if item.status in {StepStatus.FAILED, StepStatus.BLOCKED}:
                    failures += 1
        if anticipated_success is True:
            completed = min(total_steps, completed + 1)
        elif anticipated_success is False:
            failures = min(total_steps, failures + 1)

        progress = completed / max(1, total_steps)
        failure_pressure = failures / max(1, total_steps)
        evidence_count = len(state.ledger.artifacts())
        uncertainty = 1.0 / math.sqrt(1.0 + evidence_count)
        budget = state.inputs.budget
        elapsed = max(0.0, self._monotonic() - state.started_monotonic)
        pressures = (
            state.usage.steps / max(1, budget.max_steps),
            state.usage.model_calls / max(1, budget.max_model_calls),
            state.usage.tool_calls / max(1, budget.max_tool_calls),
            state.usage.total_tokens / max(1, budget.max_tokens),
            elapsed / max(1e-9, budget.max_wall_seconds),
        )
        budget_pressure = min(1.0, max(pressures))
        terminal = anticipated_success is True and completed >= total_steps
        return RuntimeGuardSignals(
            progress=max(0.0, min(1.0, progress)),
            uncertainty=max(0.0, min(1.0, uncertainty)),
            budget_pressure=max(0.0, min(1.0, budget_pressure)),
            failure_pressure=max(0.0, min(1.0, failure_pressure)),
            terminal=terminal,
        )


HardenedJeevesAgentRuntime = StrictJeevesAgentRuntime