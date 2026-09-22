"""Frontier composition for the hardened Jeeves runtime.

The strict runtime provides the mandatory enforcement path. This composition
adds generalized transition-model identities while preserving exact call
identity for authorization and audit. It also isolates learned state by a
one-way tenant/workspace scope fingerprint so experience generalizes across runs
inside a scope without silently crossing an application data boundary.

Crash recovery is conservative for side effects: an operation that reached a
real tool observation at mutating/external/high-impact risk but never reached
verification/finalization places the resumed run in reconciliation quarantine.
This prevents an autonomous replan from duplicating an ambiguous side effect.

Runtime checkpoints and the execution audit are reciprocally bound: checkpoint
metadata names the audit prefix, and a ``CHECKPOINT_BOUND`` audit event records
the complete checkpoint fingerprint *before* that checkpoint is persisted.
Resume also binds tenant/user/workspace/session identity and verifies the guard
policy, world model, and transition-model continuity.

The default frontier guard owns a monotonic model-lineage chain. That allows
legitimate learning after an older checkpoint while rejecting model resets,
out-of-band mutation, or a lineage root that is not an ancestor of the current
model. The same guard applies the high-assurance replay grammar to every audit
verification path, including resume and recovery quarantine.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable, Mapping, Sequence

from .audit_assurance import FrontierExecutionReplayVerifier
from .execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ExecutionAuditCheckpoint,
    ExecutionAuditError,
    ReplayReport,
)
from .model_based_control import CompactState
from .runtime import RunCheckpoint, RunInputs, _RunState
from .runtime_abstraction import (
    ArgumentAbstractor,
    GeneralizingRuntimeEpistemicGuard,
)
from .runtime_guard import (
    RuntimeEpistemicGuard,
    RuntimeGuardRequest,
    RuntimeGuardSignals,
)
from .semantic_lenses import SemanticFinding, SemanticObservation
from .semantic_plane import (
    SemanticLensPlane,
    SemanticPlaneLearningUpdate,
    SemanticPlaneSnapshot,
)
from .strict_runtime import StrictJeevesAgentRuntime
from .types import AgentResult, RiskTier, TerminationReason, stable_fingerprint


class ScopedGeneralizingRuntimeEpistemicGuard(GeneralizingRuntimeEpistemicGuard):
    """Scoped learning guard with assured replay and monotonic model ancestry."""

    _MODEL_LINEAGE_HISTORY = 100_000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._model_lineage_lock = threading.RLock()
        initial_model = self.transition_model.fingerprint
        self._model_lineage_count = 0
        self._model_lineage_hash = stable_fingerprint(
            {
                "kind": "jeeves-runtime-model-lineage-genesis-v1",
                "model_fingerprint": initial_model,
                "guard_policy": self.policy.fingerprint,
            }
        )
        self._model_lineage_history: deque[tuple[int, str, str]] = deque(
            [(0, self._model_lineage_hash, initial_model)],
            maxlen=self._MODEL_LINEAGE_HISTORY,
        )

    def _compact_state(
        self,
        request: RuntimeGuardRequest,
        *,
        phase: str,
        signals: RuntimeGuardSignals | None = None,
        extra_features: Mapping[str, Any] | None = None,
    ) -> CompactState:
        selected = signals or request.signals
        argument_abstraction = self.argument_abstractor.abstract(request.call.arguments)
        scope_fingerprint = stable_fingerprint(
            {
                "tenant_id": request.metadata.get("tenant_id"),
                "workspace_id": request.metadata.get("workspace_id"),
            }
        )
        features: dict[str, Any] = {
            "phase": phase,
            "tool": request.call.name,
            "risk": request.tool_spec.risk.value,
            "argument_class": stable_fingerprint(argument_abstraction)[:16],
            "learning_scope": scope_fingerprint[:16],
        }
        features.update(dict(extra_features or {}))
        return CompactState.from_signals(
            features=features,
            progress=selected.progress,
            uncertainty=selected.uncertainty,
            budget_pressure=selected.budget_pressure,
            failure_pressure=selected.failure_pressure,
            risk=request.tool_spec.risk,
            terminal=selected.terminal,
            metadata={
                "run_id": request.run_id,
                "goal_id": request.goal_id,
                "step_id": request.step_id,
                "attempt": request.attempt,
                "plan_version": request.plan_version,
                "request_fingerprint": self._request_fingerprint(request),
                "argument_abstraction": argument_abstraction,
                "argument_abstraction_policy": self.argument_abstractor.policy.fingerprint,
                "learning_scope_fingerprint": scope_fingerprint,
            },
        )

    def verify_audit(
        self,
        run_id: str,
        *,
        expected_checkpoint: ExecutionAuditCheckpoint | None = None,
        require_finalized_operations: bool = False,
    ) -> ReplayReport:
        ledger = self.audit_store.get(run_id)
        entries = () if ledger is None else ledger.entries()
        report = FrontierExecutionReplayVerifier().verify(
            entries,
            expected_run_id=run_id,
            expected_checkpoint=expected_checkpoint,
            require_finalized_operations=require_finalized_operations,
        )
        if not report.valid and self.policy.fail_closed_on_audit_error:
            summary = "; ".join(issue.message for issue in report.issues[:8])
            raise ExecutionAuditError(
                "frontier runtime audit verification failed: " + summary
            )
        return report

    def finalize(self, execution, **kwargs):
        """Serialize model mutation and advance the guard-owned lineage."""

        with self._model_lineage_lock:
            result = super().finalize(execution, **kwargs)
            current_model = self.transition_model.fingerprint
            if current_model != result.model_fingerprint:
                raise ExecutionAuditError(
                    "transition model changed outside serialized frontier finalization"
                )
            self._model_lineage_count += 1
            self._model_lineage_hash = stable_fingerprint(
                {
                    "previous": self._model_lineage_hash,
                    "count": self._model_lineage_count,
                    "operation_id": result.operation_id,
                    "experience_id": result.experience.experience_id,
                    "model_fingerprint": result.model_fingerprint,
                    "outcome": result.outcome.value,
                    "verification_score": result.verification_score,
                }
            )
            self._model_lineage_history.append(
                (
                    self._model_lineage_count,
                    self._model_lineage_hash,
                    result.model_fingerprint,
                )
            )
            return result

    def model_lineage_checkpoint(self) -> Mapping[str, Any]:
        with self._model_lineage_lock:
            current_model = self.transition_model.fingerprint
            _, _, tracked_model = self._model_lineage_history[-1]
            if current_model != tracked_model:
                raise ExecutionAuditError(
                    "transition model fingerprint diverged from guard-owned lineage"
                )
            return {
                "count": self._model_lineage_count,
                "lineage_hash": self._model_lineage_hash,
                "model_fingerprint": current_model,
            }

    def verify_model_lineage_checkpoint(
        self,
        *,
        count: int,
        lineage_hash: str,
    ) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ExecutionAuditError("invalid checkpoint model-lineage count")
        normalized = str(lineage_hash).strip().lower()
        if len(normalized) != 64 or any(
            ch not in "0123456789abcdef" for ch in normalized
        ):
            raise ExecutionAuditError("invalid checkpoint model-lineage hash")
        with self._model_lineage_lock:
            current_model = self.transition_model.fingerprint
            _, _, tracked_model = self._model_lineage_history[-1]
            if current_model != tracked_model:
                raise ExecutionAuditError(
                    "transition model changed outside guard-owned lineage"
                )
            if not any(
                item_count == count and item_hash == normalized
                for item_count, item_hash, _ in self._model_lineage_history
            ):
                raise ExecutionAuditError(
                    "checkpoint model-lineage root is not an ancestor of current model"
                )


class FrontierJeevesAgentRuntime(StrictJeevesAgentRuntime):
    """Strict runtime plus scoped generalization and crash-side-effect quarantine."""

    _QUARANTINE_KEY = "runtime_guard:recovery_quarantine"
    _SIDE_EFFECT_RISKS = {
        RiskTier.MUTATING.value,
        RiskTier.EXTERNAL.value,
        RiskTier.HIGH_IMPACT.value,
    }

    def __init__(
        self,
        *,
        argument_abstractor: ArgumentAbstractor | None = None,
        runtime_guard: RuntimeEpistemicGuard | None = None,
        semantic_plane: SemanticLensPlane | None = None,
        wall_clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        # A caller supplying a complete guard owns its exact semantics. For the
        # default construction path, let Strict build validated components and
        # then re-compose those same objects under the scoped generalizing guard
        # before any run can begin.
        super().__init__(
            runtime_guard=runtime_guard,
            wall_clock=wall_clock,
            **kwargs,
        )
        if runtime_guard is None:
            strict_guard = self.runtime_guard
            self.runtime_guard = ScopedGeneralizingRuntimeEpistemicGuard(
                self.tool_executor,
                policy=strict_guard.policy,
                world=strict_guard.world,
                transition_model=strict_guard.transition_model,
                audit_store=strict_guard.audit_store,
                wall_clock=wall_clock,
                argument_abstractor=argument_abstractor,
            )
        else:
            if runtime_guard.tool_executor is not self.tool_executor:
                raise ValueError(
                    "explicit runtime_guard must use this runtime's ToolExecutor"
                )
            if argument_abstractor is not None:
                raise ValueError(
                    "argument_abstractor cannot be combined with an explicit runtime_guard"
                )

        self.semantic_plane = semantic_plane or SemanticLensPlane()

    def analyze_semantics(
        self,
        observations: Sequence[SemanticObservation],
        *,
        findings: Sequence[SemanticFinding] = (),
        requested: Sequence[str] = (),
        base_rate: float | None = None,
        sequence: int = 0,
        domain: str | None = None,
    ) -> SemanticPlaneSnapshot:
        """Run the governed semantic plane without bypassing runtime evidence rules."""
        return self.semantic_plane.analyze(
            observations,
            findings=findings,
            requested=requested,
            base_rate=base_rate,
            sequence=sequence,
            domain=domain,
        )

    def resolve_semantic_forecast(
        self,
        forecast_id: str,
        *,
        outcome: bool,
        domain: str,
        independent_run: str,
        observed_at: float | None = None,
        observation_id: str | None = None,
        negative_control: bool = False,
    ) -> SemanticPlaneLearningUpdate:
        """Resolve a plane forecast and feed the result into lens calibration."""
        return self.semantic_plane.resolve_forecast(
            forecast_id,
            outcome=outcome,
            domain=domain,
            independent_run=independent_run,
            observed_at=observed_at,
            observation_id=observation_id,
            negative_control=negative_control,
        )

    def _state_from_checkpoint(
        self,
        inputs: RunInputs,
        checkpoint: RunCheckpoint,
    ) -> _RunState:
        self._verify_resume_identity(inputs, checkpoint)
        self.runtime_guard.verify_audit(
            checkpoint.run_id,
            require_finalized_operations=False,
        )
        self._verify_checkpoint_binding(checkpoint)
        self._verify_epistemic_roots(checkpoint)
        quarantine = self._ambiguous_side_effects(checkpoint.run_id)
        state = super()._state_from_checkpoint(inputs, checkpoint)
        if quarantine:
            state.scratch.set(
                self._QUARANTINE_KEY,
                {
                    "run_id": checkpoint.run_id,
                    "checkpoint_sequence": checkpoint.sequence,
                    "operations": list(quarantine),
                    "reason": (
                        "one or more consequential tool calls were observed before "
                        "the prior process exited but were never verifier-finalized"
                    ),
                },
                importance=1.0,
            )
            state.last_error = (
                "recovery quarantine: ambiguous side effect(s) require external reconciliation"
            )
        return state

    def _drive(self, state: _RunState) -> AgentResult:
        quarantine = state.scratch.get(self._QUARANTINE_KEY)
        if quarantine:
            self.metrics.increment("agent.tools.recovery_quarantined")
            state.trace.emit(
                "run.recovery_quarantined",
                dict(quarantine),
            )
            return self._finish_failure(
                state,
                TerminationReason.CONFIRMATION_REQUIRED,
                "A prior consequential tool call may already have taken effect; autonomous replanning is blocked until external state is reconciled.",
                metadata={
                    "recovery_quarantine": quarantine,
                    "required_action": "reconcile_external_state_before_new_execution",
                },
            )
        return super()._drive(state)

    def _checkpoint(self, state: _RunState) -> RunCheckpoint:
        """Persist after reciprocally binding checkpoint, audit, and model roots."""

        audit = self.runtime_guard.audit_checkpoint(state.run_id)
        lineage = (
            self.runtime_guard.model_lineage_checkpoint()
            if isinstance(self.runtime_guard, ScopedGeneralizingRuntimeEpistemicGuard)
            else None
        )
        world_fingerprint = self.runtime_guard.world.snapshot(persist=False).fingerprint
        state.checkpoint_sequence += 1
        scratch = {
            entry.key: {
                "value": entry.value,
                "importance": entry.importance,
            }
            for entry in state.scratch.entries()
        }
        metadata = {
            "tenant_id": state.inputs.tenant_id,
            "user_id": state.inputs.user_id,
            "workspace_id": state.inputs.workspace_id,
            "session_id": state.inputs.session_id,
            "evidence_fingerprint": state.ledger.fingerprint,
            "strict_runtime": True,
            "frontier_runtime": True,
            "runtime_guard_policy": self.runtime_guard.policy.fingerprint,
            "execution_audit_head": audit.head_hash,
            "execution_audit_events": audit.event_count,
            "execution_audit_checkpoint": audit.checkpoint_fingerprint,
            "transition_model_fingerprint": self.runtime_guard.transition_model.fingerprint,
            "world_model_fingerprint": world_fingerprint,
            "semantic_plane_fingerprint": self.semantic_plane.fingerprint,
        }
        if lineage is not None:
            metadata.update(
                {
                    "transition_model_lineage_count": lineage["count"],
                    "transition_model_lineage_hash": lineage["lineage_hash"],
                }
            )
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
            metadata=metadata,
        )
        binding_payload = {
            "frontier_binding_version": 2,
            "checkpoint_sequence": checkpoint.sequence,
            "checkpoint_fingerprint": checkpoint.fingerprint,
            "audit_head_before": audit.head_hash,
            "audit_events_before": audit.event_count,
            "audit_checkpoint_before": audit.checkpoint_fingerprint,
            "runtime_guard_policy": self.runtime_guard.policy.fingerprint,
            "transition_model_fingerprint": self.runtime_guard.transition_model.fingerprint,
            "world_model_fingerprint": world_fingerprint,
            "semantic_plane_fingerprint": self.semantic_plane.fingerprint,
        }
        if lineage is not None:
            binding_payload.update(
                {
                    "transition_model_lineage_count": lineage["count"],
                    "transition_model_lineage_hash": lineage["lineage_hash"],
                }
            )
        ledger = self.runtime_guard.audit_store.get_or_create(state.run_id)
        ledger.append(
            AuditEventKind.CHECKPOINT_BOUND,
            binding_payload,
            severity=AuditSeverity.SECURITY,
        )
        self.checkpointer.save(checkpoint)
        self.metrics.increment("agent.checkpoints.saved")
        self.metrics.increment("agent.checkpoints.audit_bound")
        return checkpoint

    @staticmethod
    def _verify_resume_identity(inputs: RunInputs, checkpoint: RunCheckpoint) -> None:
        expected = {
            "tenant_id": inputs.tenant_id,
            "user_id": inputs.user_id,
            "workspace_id": inputs.workspace_id,
            "session_id": inputs.session_id,
        }
        actual = {key: checkpoint.metadata.get(key) for key in expected}
        mismatches = [
            key
            for key in expected
            if actual.get(key) != expected[key]
        ]
        if mismatches:
            raise ExecutionAuditError(
                "resume identity/scope mismatch: " + ", ".join(sorted(mismatches))
            )
        if checkpoint.metadata.get("strict_runtime") is not True:
            raise ExecutionAuditError(
                "checkpoint was not created by the strict runtime"
            )
        if checkpoint.metadata.get("frontier_runtime") is not True:
            raise ExecutionAuditError(
                "checkpoint was not created by the frontier runtime"
            )

    def _verify_epistemic_roots(self, checkpoint: RunCheckpoint) -> None:
        expected_policy = checkpoint.metadata.get("runtime_guard_policy")
        if expected_policy != self.runtime_guard.policy.fingerprint:
            raise ExecutionAuditError("runtime guard policy fingerprint changed on resume")

        expected_world = checkpoint.metadata.get("world_model_fingerprint")
        current_world = self.runtime_guard.world.snapshot(persist=False).fingerprint
        if expected_world != current_world:
            raise ExecutionAuditError("world model fingerprint changed on resume")

        expected_semantic_plane = checkpoint.metadata.get("semantic_plane_fingerprint")
        if (
            expected_semantic_plane is not None
            and expected_semantic_plane != self.semantic_plane.fingerprint
        ):
            raise ExecutionAuditError(
                "semantic plane contract fingerprint changed on resume"
            )

        if isinstance(self.runtime_guard, ScopedGeneralizingRuntimeEpistemicGuard):
            try:
                lineage_count = int(
                    checkpoint.metadata["transition_model_lineage_count"]
                )
                lineage_hash = str(
                    checkpoint.metadata["transition_model_lineage_hash"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ExecutionAuditError(
                    "checkpoint is missing transition-model lineage metadata"
                ) from exc
            self.runtime_guard.verify_model_lineage_checkpoint(
                count=lineage_count,
                lineage_hash=lineage_hash,
            )
            return

        # Compatibility fallback for an explicitly supplied custom guard. The
        # default package runtime never takes this path.
        expected_model = checkpoint.metadata.get("transition_model_fingerprint")
        expected_events = int(checkpoint.metadata.get("execution_audit_events", 0))
        ledger = self.runtime_guard.audit_store.get(checkpoint.run_id)
        if ledger is None:
            raise ExecutionAuditError("transition-model resume has no audit ledger")
        entries = ledger.entries()
        for entry in entries[expected_events:]:
            if entry.kind is not AuditEventKind.TRANSITION_LEARNED:
                continue
            candidate = entry.payload.get("model_fingerprint")
            if isinstance(candidate, str) and candidate:
                expected_model = candidate
        current_model = self.runtime_guard.transition_model.fingerprint
        if expected_model != current_model:
            raise ExecutionAuditError(
                "transition model fingerprint does not match latest audit-proven model root"
            )

    def _verify_checkpoint_binding(self, checkpoint: RunCheckpoint) -> None:
        expected_head = str(
            checkpoint.metadata.get("execution_audit_head", "0" * 64)
        )
        expected_events = int(
            checkpoint.metadata.get("execution_audit_events", 0)
        )
        ledger = self.runtime_guard.audit_store.get(checkpoint.run_id)
        if ledger is None:
            raise ExecutionAuditError(
                "frontier checkpoint has no corresponding execution audit ledger"
            )
        entries = ledger.entries()
        if len(entries) <= expected_events:
            raise ExecutionAuditError(
                "frontier checkpoint is missing its reciprocal audit binding"
            )
        candidates = entries[expected_events:]
        for entry in candidates:
            if entry.kind is not AuditEventKind.CHECKPOINT_BOUND:
                continue
            payload = entry.payload
            if payload.get("checkpoint_sequence") != checkpoint.sequence:
                continue
            if payload.get("checkpoint_fingerprint") != checkpoint.fingerprint:
                continue
            if payload.get("audit_head_before") != expected_head:
                continue
            if payload.get("audit_events_before") != expected_events:
                continue
            if payload.get("runtime_guard_policy") != checkpoint.metadata.get(
                "runtime_guard_policy"
            ):
                continue
            if payload.get("transition_model_fingerprint") != checkpoint.metadata.get(
                "transition_model_fingerprint"
            ):
                continue
            if payload.get("world_model_fingerprint") != checkpoint.metadata.get(
                "world_model_fingerprint"
            ):
                continue
            checkpoint_semantic_plane = checkpoint.metadata.get(
                "semantic_plane_fingerprint"
            )
            if (
                checkpoint_semantic_plane is not None
                and payload.get("semantic_plane_fingerprint")
                != checkpoint_semantic_plane
            ):
                continue
            checkpoint_lineage = checkpoint.metadata.get(
                "transition_model_lineage_hash"
            )
            if checkpoint_lineage is not None and payload.get(
                "transition_model_lineage_hash"
            ) != checkpoint_lineage:
                continue
            return
        raise ExecutionAuditError(
            "frontier checkpoint fingerprint is not reciprocally bound in audit chain"
        )

    def _ambiguous_side_effects(self, run_id: str) -> tuple[str, ...]:
        ledger = self.runtime_guard.audit_store.get(run_id)
        if ledger is None:
            return ()
        report = self.runtime_guard.verify_audit(
            run_id,
            require_finalized_operations=False,
        )
        ambiguous: list[str] = []
        for operation in report.operations:
            if operation.finalized or operation.terminal_kind is not None:
                continue
            if operation.observation_fingerprint is None:
                continue
            entries = ledger.operation_entries(operation.operation_id)
            risk = None
            for entry in entries:
                if entry.kind is AuditEventKind.INTENT_BOUND:
                    risk = entry.payload.get("risk")
                    break
            if risk in self._SIDE_EFFECT_RISKS:
                ambiguous.append(operation.operation_id)
        return tuple(sorted(set(ambiguous)))


HardenedJeevesAgentRuntime = FrontierJeevesAgentRuntime