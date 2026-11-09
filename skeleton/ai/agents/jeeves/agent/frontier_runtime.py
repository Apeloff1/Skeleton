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
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

from .audit_assurance import FrontierExecutionReplayVerifier
from .cortex import JeevesCortex
from .execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ExecutionAuditCheckpoint,
    ExecutionAuditError,
    ReplayReport,
)
from .model_based_control import CompactState
from .epistemic_frontier import KnowledgeObligation
from .frontier_control_plane import FrontierCognitiveControlPlane
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
from .semantic_frontier import LensInteractionKind
from .semantic_lenses import SemanticFinding, SemanticObservation
from .semantic_plane import (
    SemanticLensPlane,
    SemanticPlaneLearningUpdate,
    SemanticPlaneSnapshot,
)
from .semantic_topology_learning import (
    SemanticTopologyLearningSnapshot,
    SemanticTopologyLearningState,
    TopologyBridgePrediction,
    TopologyBridgeReport,
    TopologyBridgeTrial,
)
from .semantic_research_bridge import (
    SemanticTopologyResearchBridge,
    SemanticTopologyResearchUpdate,
)
from .semantic_scope import (
    ScopedSemanticPlanePool,
    ScopedSemanticTopologyState,
    SemanticLearningScope,
)
from .strict_runtime import StrictJeevesAgentRuntime
from .types import AgentResult, RiskTier, StepStatus, TerminationReason, stable_fingerprint


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
    _CORTEX_ASSESSMENT_KEY = "cortex:assessment"
    _CORTEX_ERROR_KEY = "cortex:error"
    _RISK_ORDER = {
        RiskTier.READ_ONLY: 0,
        RiskTier.REVERSIBLE: 1,
        RiskTier.MUTATING: 2,
        RiskTier.EXTERNAL: 3,
        RiskTier.HIGH_IMPACT: 4,
    }

    def __init__(
        self,
        *,
        argument_abstractor: ArgumentAbstractor | None = None,
        runtime_guard: RuntimeEpistemicGuard | None = None,
        semantic_plane: SemanticLensPlane | None = None,
        semantic_scope_pool: ScopedSemanticPlanePool | None = None,
        semantic_scoping_enabled: bool = True,
        cortex: JeevesCortex | None = None,
        cortex_enabled: bool = True,
        cortex_required: bool = False,
        wall_clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        if not isinstance(semantic_scoping_enabled, bool):
            raise TypeError("semantic_scoping_enabled must be boolean")
        if not isinstance(cortex_enabled, bool):
            raise TypeError("cortex_enabled must be boolean")
        if not isinstance(cortex_required, bool):
            raise TypeError("cortex_required must be boolean")
        if cortex_required and not cortex_enabled:
            raise ValueError("cortex_required cannot be true when cortex is disabled")
        if cortex is not None and not isinstance(cortex, JeevesCortex):
            raise TypeError("cortex must be JeevesCortex or None")
        if not cortex_enabled and cortex is not None:
            raise ValueError("cortex cannot be supplied when cortex_enabled is false")
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
        if (
            semantic_scope_pool is not None
            and not isinstance(
                semantic_scope_pool,
                ScopedSemanticPlanePool,
            )
        ):
            raise TypeError(
                "semantic_scope_pool must be ScopedSemanticPlanePool or None"
            )
        if (
            semantic_scope_pool is not None
            and semantic_scope_pool.template.fingerprint
            != self.semantic_plane.fingerprint
        ):
            raise ValueError(
                "semantic_scope_pool template contract differs from semantic_plane"
            )
        self.semantic_scoping_enabled = semantic_scoping_enabled
        self.semantic_scope_pool = (
            semantic_scope_pool
            or ScopedSemanticPlanePool(self.semantic_plane)
        )
        self.cortex_required = cortex_required
        self.cortex = cortex if cortex_enabled else None
        if cortex_enabled and self.cortex is None:
            self.cortex = JeevesCortex(
                clock=wall_clock,
                monotonic=self._monotonic,
            )
        self._cortex_lock = threading.RLock()
        self._cortex_assessments: dict[str, Mapping[str, Any]] = {}

    def semantic_learning_scope(
        self,
        inputs: RunInputs,
    ) -> SemanticLearningScope:
        if not isinstance(inputs, RunInputs):
            raise TypeError("inputs must be RunInputs")
        return SemanticLearningScope(
            tenant_id=inputs.tenant_id,
            user_id=inputs.user_id,
            workspace_id=inputs.workspace_id,
        )

    def semantic_plane_for(
        self,
        inputs: RunInputs,
    ) -> SemanticLensPlane:
        """Return mutable semantic state isolated to one learning scope."""

        if not isinstance(inputs, RunInputs):
            raise TypeError("inputs must be RunInputs")
        if not self.semantic_scoping_enabled:
            return self.semantic_plane
        return self.semantic_scope_pool.get(
            inputs.tenant_id,
            inputs.user_id,
            inputs.workspace_id,
        )

    def semantic_plane_for_scope(
        self,
        tenant_id: str,
        user_id: str,
        workspace_id: str,
    ) -> SemanticLensPlane:
        if not self.semantic_scoping_enabled:
            return self.semantic_plane
        return self.semantic_scope_pool.get(
            tenant_id,
            user_id,
            workspace_id,
        )

    def analyze_scoped_semantics(
        self,
        inputs: RunInputs,
        observations: Sequence[SemanticObservation],
        *,
        findings: Sequence[SemanticFinding] = (),
        requested: Sequence[str] = (),
        base_rate: float | None = None,
        sequence: int = 0,
    ) -> SemanticPlaneSnapshot:
        return self.semantic_plane_for(inputs).analyze(
            observations,
            findings=findings,
            requested=requested,
            base_rate=base_rate,
            sequence=sequence,
        )

    def declare_scoped_semantic_topology_candidate_prediction(
        self,
        inputs: RunInputs,
        candidate_id: str,
        *,
        kind: LensInteractionKind,
        predicted_probability: float,
        domain: str,
        independent_run: str,
        predicted_at: float,
        negative_control: bool = False,
        source_finding_ids: Sequence[str] = (),
        source_forecast_ids: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgePrediction:
        plane = self.semantic_plane_for(inputs)
        return plane.declare_topology_candidate_prediction(
            candidate_id,
            kind=kind,
            predicted_probability=predicted_probability,
            domain=domain,
            independent_run=independent_run,
            predicted_at=predicted_at,
            negative_control=negative_control,
            source_finding_ids=source_finding_ids,
            source_forecast_ids=source_forecast_ids,
            evidence_ids=evidence_ids,
            metadata=metadata,
        )

    def resolve_scoped_semantic_topology_prediction(
        self,
        inputs: RunInputs,
        prediction_id: str,
        *,
        outcome: bool,
        observed_at: float,
        outcome_evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgeReport:
        plane = self.semantic_plane_for(inputs)
        return plane.resolve_topology_bridge_prediction(
            prediction_id,
            outcome=outcome,
            observed_at=observed_at,
            outcome_evidence_ids=outcome_evidence_ids,
            metadata=metadata,
        )

    def scoped_semantic_topology_learning_summary(
        self,
        inputs: RunInputs,
    ) -> Mapping[str, Any]:
        return self.semantic_plane_for(
            inputs
        ).topology_learning_summary()

    def scoped_semantic_topology_learning_diagnostics(
        self,
        inputs: RunInputs,
        *,
        candidate_id: str | None = None,
        kind: LensInteractionKind | None = None,
        limit: int = 100,
    ) -> Mapping[str, Any]:
        return self.semantic_plane_for(
            inputs
        ).topology_learning_diagnostics(
            candidate_id=candidate_id,
            kind=kind,
            limit=limit,
        )

    def export_scoped_semantic_topology_learning_state(
        self,
        inputs: RunInputs,
    ) -> ScopedSemanticTopologyState:
        return self.semantic_scope_pool.export_topology_state(
            inputs.tenant_id,
            inputs.user_id,
            inputs.workspace_id,
        )

    def restore_scoped_semantic_topology_learning_state(
        self,
        inputs: RunInputs,
        state: ScopedSemanticTopologyState | Mapping[str, Any],
    ) -> SemanticTopologyLearningSnapshot:
        return self.semantic_scope_pool.restore_topology_state(
            inputs.tenant_id,
            inputs.user_id,
            inputs.workspace_id,
            state,
        )

    def semantic_scope_diagnostics(self) -> Mapping[str, Any]:
        return {
            "enabled": self.semantic_scoping_enabled,
            "pool": self.semantic_scope_pool.diagnostics(),
            "global_compatibility_plane": {
                "contract_fingerprint": self.semantic_plane.fingerprint,
                "topology_learning_fingerprint": (
                    self.semantic_plane.topology_learning.fingerprint
                ),
            },
        }

    def analyze_semantics(
        self,
        observations: Sequence[SemanticObservation],
        *,
        findings: Sequence[SemanticFinding] = (),
        requested: Sequence[str] = (),
        base_rate: float | None = None,
        sequence: int = 0,
    ) -> SemanticPlaneSnapshot:
        """Run the governed semantic plane without bypassing runtime evidence rules."""
        return self.semantic_plane.analyze(
            observations,
            findings=findings,
            requested=requested,
            base_rate=base_rate,
            sequence=sequence,
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

    def declare_semantic_topology_candidate_prediction(
        self,
        candidate_id: str,
        *,
        kind: LensInteractionKind,
        predicted_probability: float,
        domain: str,
        independent_run: str,
        predicted_at: float,
        negative_control: bool = False,
        source_finding_ids: Sequence[str] = (),
        source_forecast_ids: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgePrediction:
        """Create one canonical predeclared semantic topology experiment."""

        return self.semantic_plane.declare_topology_candidate_prediction(
            candidate_id,
            kind=kind,
            predicted_probability=predicted_probability,
            domain=domain,
            independent_run=independent_run,
            predicted_at=predicted_at,
            negative_control=negative_control,
            source_finding_ids=source_finding_ids,
            source_forecast_ids=source_forecast_ids,
            evidence_ids=evidence_ids,
            metadata=metadata,
        )

    def unresolved_semantic_topology_predictions(
        self,
        *,
        candidate_id: str | None = None,
    ) -> tuple[TopologyBridgePrediction, ...]:
        return self.semantic_plane.unresolved_topology_predictions(
            candidate_id=candidate_id,
        )

    def declare_semantic_topology_candidate_prediction(
        self,
        candidate_id: str,
        *,
        kind: LensInteractionKind,
        predicted_probability: float,
        domain: str,
        independent_run: str,
        predicted_at: float,
        negative_control: bool = False,
        source_finding_ids: Sequence[str] = (),
        source_forecast_ids: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgePrediction:
        """Create and declare one canonical topology experiment prediction."""

        return self.semantic_plane.declare_topology_candidate_prediction(
            candidate_id,
            kind=kind,
            predicted_probability=predicted_probability,
            domain=domain,
            independent_run=independent_run,
            predicted_at=predicted_at,
            negative_control=negative_control,
            source_finding_ids=source_finding_ids,
            source_forecast_ids=source_forecast_ids,
            evidence_ids=evidence_ids,
            metadata=metadata,
        )

    def unresolved_semantic_topology_predictions(
        self,
        *,
        candidate_id: str | None = None,
    ) -> tuple[TopologyBridgePrediction, ...]:
        """List predeclared topology predictions still awaiting outcomes."""

        return self.semantic_plane.unresolved_topology_predictions(
            candidate_id=candidate_id,
        )

    def declare_semantic_topology_prediction(
        self,
        prediction: TopologyBridgePrediction,
    ) -> TopologyBridgePrediction:
        """Declare a topology bridge prediction before observing its outcome."""

        return self.semantic_plane.declare_topology_bridge_prediction(
            prediction
        )

    def resolve_semantic_topology_prediction(
        self,
        prediction_id: str,
        *,
        outcome: bool,
        observed_at: float,
        outcome_evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgeReport:
        """Resolve one declared topology bridge prediction exactly once."""

        return self.semantic_plane.resolve_topology_bridge_prediction(
            prediction_id,
            outcome=outcome,
            observed_at=observed_at,
            outcome_evidence_ids=outcome_evidence_ids,
            metadata=metadata,
        )

    def record_semantic_topology_trial(
        self,
        trial: TopologyBridgeTrial,
    ) -> TopologyBridgeReport:
        """Import a resolved trial whose prediction is already in custody."""

        return self.semantic_plane.record_topology_bridge_trial(trial)

    def semantic_topology_learning_diagnostics(
        self,
        *,
        candidate_id: str | None = None,
        kind: LensInteractionKind | None = None,
        limit: int = 100,
    ) -> Mapping[str, Any]:
        """Return bounded semantic topology-learning diagnostics."""

        return self.semantic_plane.topology_learning_diagnostics(
            candidate_id=candidate_id,
            kind=kind,
            limit=limit,
        )

    def semantic_topology_research_obligations(
        self,
        *,
        limit: int = 24,
        minimum_candidate_score: float = 0.18,
        include_rejected: bool = False,
    ) -> tuple[KnowledgeObligation, ...]:
        """Return semantic-topology gaps as typed research obligations."""

        return self.semantic_plane.topology_research_obligations(
            limit=limit,
            minimum_candidate_score=minimum_candidate_score,
            include_rejected=include_rejected,
        )

    def map_semantic_topology_research(
        self,
        control_plane: FrontierCognitiveControlPlane,
        *,
        limit: int = 24,
        minimum_candidate_score: float = 0.18,
        include_rejected: bool = False,
        dependencies: Mapping[str, Sequence[str]] | None = None,
    ) -> SemanticTopologyResearchUpdate:
        """Refresh topology research debt into Jeeves' durable research agenda."""

        bridge = SemanticTopologyResearchBridge(
            self.semantic_plane.topology_learning,
            control_plane,
        )
        return bridge.refresh(
            limit=limit,
            minimum_candidate_score=minimum_candidate_score,
            include_rejected=include_rejected,
            dependencies=dependencies,
        )

    def export_semantic_topology_learning_state(
        self,
    ) -> SemanticTopologyLearningState:
        """Export contract-bound semantic topology learning state."""

        return self.semantic_plane.export_topology_learning_state()

    def restore_semantic_topology_learning_state(
        self,
        state: SemanticTopologyLearningState | Mapping[str, Any],
    ) -> SemanticTopologyLearningSnapshot:
        """Restore semantic topology state after full contract validation."""

        return self.semantic_plane.restore_topology_learning_state(state)

    def semantic_topology_learning_summary(self) -> Mapping[str, Any]:
        """Return bounded bridge-learning state without promoting it to evidence."""

        return self.semantic_plane.topology_learning_summary()

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
        self._restore_cortex_advisory(state, checkpoint)
        return state

    def _drive(self, state: _RunState) -> AgentResult:
        quarantine = state.scratch.get(self._QUARANTINE_KEY)
        if quarantine:
            self.metrics.increment("agent.tools.recovery_quarantined")
            state.trace.emit(
                "run.recovery_quarantined",
                dict(quarantine),
            )
            result = self._finish_failure(
                state,
                TerminationReason.CONFIRMATION_REQUIRED,
                "A prior consequential tool call may already have taken effect; autonomous replanning is blocked until external state is reconciled.",
                metadata={
                    "recovery_quarantine": quarantine,
                    "required_action": "reconcile_external_state_before_new_execution",
                },
            )
        else:
            result = super()._drive(state)
        return self._observe_cortex_result(state, result)

    def _checkpoint(self, state: _RunState) -> RunCheckpoint:
        """Persist after reciprocally binding checkpoint, audit, and model roots."""

        audit = self.runtime_guard.audit_checkpoint(state.run_id)
        lineage = (
            self.runtime_guard.model_lineage_checkpoint()
            if isinstance(self.runtime_guard, ScopedGeneralizingRuntimeEpistemicGuard)
            else None
        )
        world_fingerprint = self.runtime_guard.world.snapshot(
            persist=False
        ).fingerprint
        semantic_scope = self.semantic_learning_scope(state.inputs)
        semantic_plane = self.semantic_plane_for(state.inputs)
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
            "semantic_scoping_enabled": self.semantic_scoping_enabled,
            "semantic_learning_scope_fingerprint": (
                semantic_scope.fingerprint
            ),
            "semantic_plane_fingerprint": semantic_plane.fingerprint,
            "semantic_runtime_state_fingerprint": (
                semantic_plane.runtime_state_fingerprint
            ),
            "semantic_topology_learning_fingerprint": (
                semantic_plane.topology_learning.fingerprint
            ),
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
            "frontier_binding_version": 5,
            "checkpoint_sequence": checkpoint.sequence,
            "checkpoint_fingerprint": checkpoint.fingerprint,
            "audit_head_before": audit.head_hash,
            "audit_events_before": audit.event_count,
            "audit_checkpoint_before": audit.checkpoint_fingerprint,
            "runtime_guard_policy": self.runtime_guard.policy.fingerprint,
            "transition_model_fingerprint": self.runtime_guard.transition_model.fingerprint,
            "world_model_fingerprint": world_fingerprint,
            "semantic_scoping_enabled": self.semantic_scoping_enabled,
            "semantic_learning_scope_fingerprint": (
                semantic_scope.fingerprint
            ),
            "semantic_plane_fingerprint": semantic_plane.fingerprint,
            "semantic_runtime_state_fingerprint": (
                semantic_plane.runtime_state_fingerprint
            ),
            "semantic_topology_learning_fingerprint": (
                semantic_plane.topology_learning.fingerprint
            ),
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
        self._observe_cortex_checkpoint(state, checkpoint)
        return checkpoint

    def _ensure_cortex_run(
        self,
        state: _RunState,
        checkpoint_sequence: int,
    ) -> bool:
        if self.cortex is None:
            return False
        try:
            self.cortex.begin(
                state.inputs,
                run_id=state.run_id,
                evidence_ledger=state.ledger,
            )
            return True
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            self.metrics.increment("agent.cortex.checkpoint_errors")
            error = {
                "stage": "bind_run",
                "error_type": type(exc).__name__,
                "message": str(exc)[:512],
                "checkpoint_sequence": checkpoint_sequence,
                "authority": "advisory_only",
            }
            state.scratch.set(self._CORTEX_ERROR_KEY, error, importance=0.90)
            state.trace.emit("cortex.error", error)
            if self.cortex_required:
                raise
            return False

    def _restore_cortex_advisory(
        self,
        state: _RunState,
        checkpoint: RunCheckpoint,
    ) -> None:
        if self.cortex is None:
            return
        if not self._ensure_cortex_run(state, checkpoint.sequence):
            return
        with self._cortex_lock:
            cached = self._cortex_assessments.get(state.run_id)
        if cached is not None and cached.get("checkpoint_sequence") == checkpoint.sequence:
            state.scratch.set(
                self._CORTEX_ASSESSMENT_KEY,
                cached,
                importance=0.95,
            )
            state.scratch.delete(self._CORTEX_ERROR_KEY)
            return
        self._observe_cortex_checkpoint(state, checkpoint)

    def _observe_cortex_checkpoint(
        self,
        state: _RunState,
        checkpoint: RunCheckpoint,
    ) -> Mapping[str, Any] | None:
        if self.cortex is None:
            return None
        if not self._ensure_cortex_run(state, checkpoint.sequence):
            return None
        try:
            assessment = self.cortex.observe_checkpoint(
                state.inputs,
                checkpoint,
                current_risk=self._cortex_current_risk(state),
            )
            payload = {
                "schema_version": 1,
                "authority": "advisory_only",
                "checkpoint_sequence": checkpoint.sequence,
                "checkpoint_fingerprint": checkpoint.fingerprint,
                "decision_id": assessment.decision.decision_id,
                "mode": assessment.decision.mode.value,
                "score": assessment.decision.score,
                "directive": assessment.decision.directive,
                "hard_stop": assessment.decision.hard_stop,
                "requires_confirmation": assessment.decision.requires_confirmation,
                "reasons": [reason.value for reason in assessment.decision.reasons],
                "recommended_skill_id": assessment.recommended_skill_id,
                "world_fingerprint": assessment.world_fingerprint,
                "probes": [
                    {
                        "probe_id": probe.probe_id,
                        "proposition_id": probe.proposition_id,
                        "expected_information_gain_bits": probe.expected_information_gain_bits,
                        "priority": probe.priority,
                    }
                    for probe in assessment.probes[:4]
                ],
                "notes": list(assessment.notes[:8]),
            }
            with self._cortex_lock:
                self._cortex_assessments[state.run_id] = payload
            state.scratch.set(
                self._CORTEX_ASSESSMENT_KEY,
                payload,
                importance=0.95,
            )
            state.scratch.delete(self._CORTEX_ERROR_KEY)
            state.trace.emit(
                "cortex.checkpoint_assessed",
                {
                    "checkpoint_sequence": checkpoint.sequence,
                    "decision_id": assessment.decision.decision_id,
                    "mode": assessment.decision.mode.value,
                    "score": assessment.decision.score,
                    "hard_stop": assessment.decision.hard_stop,
                    "recommended_skill_id": assessment.recommended_skill_id,
                    "probe_count": len(assessment.probes),
                    "authority": "advisory_only",
                },
            )
            self.metrics.increment("agent.cortex.checkpoints_assessed")
            return payload
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            self.metrics.increment("agent.cortex.checkpoint_errors")
            error = {
                "stage": "checkpoint",
                "error_type": type(exc).__name__,
                "message": str(exc)[:512],
                "checkpoint_sequence": checkpoint.sequence,
                "authority": "advisory_only",
            }
            state.scratch.set(self._CORTEX_ERROR_KEY, error, importance=0.90)
            state.trace.emit("cortex.error", error)
            if self.cortex_required:
                raise
            return None

    def _observe_cortex_result(
        self,
        state: _RunState,
        result: AgentResult,
    ) -> AgentResult:
        if self.cortex is None:
            return result
        try:
            verification_scores, action_costs, action_risks = self._cortex_learning_signals(
                state.run_id
            )
            report = self.cortex.observe_result(
                state.inputs,
                result,
                verification_scores=verification_scores,
                action_costs=action_costs,
                action_risks=action_risks,
            )
            metadata = dict(result.metadata)
            metadata["cortex"] = {
                "status": "observed",
                "authority": "advisory_only",
                "report_fingerprint": report.report_fingerprint,
                "world_fingerprint": report.world_fingerprint,
                "belief_count": report.belief_count,
                "hypothesis_count": report.hypothesis_count,
                "world_entropy_bits": report.world_entropy_bits,
                "decision_count": len(report.decisions),
                "learned_skill_ids": list(report.learned_skill_ids),
                "verified_tool_signal_count": len(verification_scores),
                "cost_bound_tool_signal_count": len(action_costs),
                "risk_bound_tool_signal_count": len(action_risks),
                "anomalies": list(report.anomalies),
            }
            self.metrics.increment("agent.cortex.results_observed")
            return replace(result, metadata=metadata)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            self.metrics.increment("agent.cortex.result_errors")
            if self.cortex_required:
                raise
            metadata = dict(result.metadata)
            metadata["cortex"] = {
                "status": "degraded",
                "authority": "advisory_only",
                "error_type": type(exc).__name__,
                "message": str(exc)[:512],
            }
            return replace(result, metadata=metadata)

    def _cortex_learning_signals(
        self,
        run_id: str,
    ) -> tuple[dict[str, float], dict[str, float], dict[str, RiskTier]]:
        ledger = self.runtime_guard.audit_store.get(run_id)
        if ledger is None:
            return {}, {}, {}

        by_operation: dict[str, dict[str, Any]] = {}
        for entry in ledger.entries():
            if entry.operation_id is None:
                continue
            record = by_operation.setdefault(entry.operation_id, {})
            if entry.kind is AuditEventKind.INTENT_BOUND:
                call_id = entry.payload.get("call_id")
                risk = entry.payload.get("risk")
                if isinstance(call_id, str) and call_id:
                    record["call_id"] = call_id
                try:
                    if risk is not None:
                        record["risk"] = (
                            risk
                            if isinstance(risk, RiskTier)
                            else RiskTier(str(risk))
                        )
                except ValueError:
                    pass
            elif entry.kind is AuditEventKind.EXECUTION_FINALIZED:
                score = entry.payload.get("verification_score")
                try:
                    normalized = float(score)
                except (TypeError, ValueError):
                    continue
                if 0.0 <= normalized <= 1.0:
                    record["verification_score"] = normalized

        finalization_costs = {
            item.operation_id: item.experience.cost
            for item in self.runtime_guard.finalizations(run_id)
        }
        verification_scores: dict[str, float] = {}
        action_costs: dict[str, float] = {}
        action_risks: dict[str, RiskTier] = {}
        for operation_id, record in by_operation.items():
            call_id = record.get("call_id")
            if not isinstance(call_id, str) or not call_id:
                continue
            score = record.get("verification_score")
            if isinstance(score, float):
                verification_scores[call_id] = score
            cost = finalization_costs.get(operation_id)
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                action_costs[call_id] = max(0.0, float(cost))
            risk = record.get("risk")
            if isinstance(risk, RiskTier):
                action_risks[call_id] = risk
        return verification_scores, action_costs, action_risks

    def _cortex_current_risk(self, state: _RunState) -> RiskTier:
        if state.plan is None:
            return RiskTier.READ_ONLY
        running = [
            step for step in state.plan.steps
            if step.status is StepStatus.RUNNING
        ]
        candidates = running or list(state.plan.ready_steps())
        if not candidates:
            return RiskTier.READ_ONLY
        risks: list[RiskTier] = []
        for step in candidates:
            risk = step.risk
            if step.tool is not None:
                registered = self.tools.get(step.tool)
                if registered is not None:
                    host_risk = registered.spec.risk
                    if self._RISK_ORDER[host_risk] > self._RISK_ORDER[risk]:
                        risk = host_risk
            risks.append(risk)
        return max(risks, key=lambda risk: self._RISK_ORDER[risk])

    def cortex_summary(self) -> Mapping[str, Any]:
        if self.cortex is None:
            return {
                "enabled": False,
                "required": self.cortex_required,
            }
        summary = dict(self.cortex.global_summary())
        summary.update(
            {
                "enabled": True,
                "required": self.cortex_required,
                "authority": "advisory_only",
            }
        )
        return summary

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

        checkpoint_scoping = checkpoint.metadata.get(
            "semantic_scoping_enabled"
        )
        if checkpoint_scoping is None:
            raise ExecutionAuditError(
                "checkpoint is missing semantic scoping mode"
            )
        if bool(checkpoint_scoping) != self.semantic_scoping_enabled:
            raise ExecutionAuditError(
                "semantic scoping mode changed on resume"
            )

        try:
            semantic_scope = SemanticLearningScope(
                tenant_id=str(checkpoint.metadata["tenant_id"]),
                user_id=str(checkpoint.metadata["user_id"]),
                workspace_id=str(checkpoint.metadata["workspace_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExecutionAuditError(
                "checkpoint is missing semantic learning scope metadata"
            ) from exc
        expected_scope = checkpoint.metadata.get(
            "semantic_learning_scope_fingerprint"
        )
        if expected_scope != semantic_scope.fingerprint:
            raise ExecutionAuditError(
                "semantic learning scope fingerprint mismatch"
            )
        semantic_plane = self.semantic_plane_for_scope(
            semantic_scope.tenant_id,
            semantic_scope.user_id,
            semantic_scope.workspace_id,
        )

        expected_semantic_plane = checkpoint.metadata.get(
            "semantic_plane_fingerprint"
        )
        if (
            expected_semantic_plane is None
            or expected_semantic_plane != semantic_plane.fingerprint
        ):
            raise ExecutionAuditError(
                "semantic plane contract fingerprint changed on resume"
            )

        expected_semantic_state = checkpoint.metadata.get(
            "semantic_runtime_state_fingerprint"
        )
        if expected_semantic_state is None:
            raise ExecutionAuditError(
                "checkpoint is missing semantic runtime state root"
            )
        if (
            expected_semantic_state
            != semantic_plane.runtime_state_fingerprint
        ):
            raise ExecutionAuditError(
                "semantic runtime state fingerprint changed on resume"
            )

        expected_topology_learning = checkpoint.metadata.get(
            "semantic_topology_learning_fingerprint"
        )
        if expected_topology_learning is None:
            raise ExecutionAuditError(
                "checkpoint is missing semantic topology learning root"
            )
        current_topology_learning = (
            semantic_plane.topology_learning.fingerprint
        )
        if expected_topology_learning != current_topology_learning:
            raise ExecutionAuditError(
                "semantic topology learning fingerprint changed on resume"
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
            if payload.get(
                "semantic_scoping_enabled"
            ) != checkpoint.metadata.get("semantic_scoping_enabled"):
                continue
            if payload.get(
                "semantic_learning_scope_fingerprint"
            ) != checkpoint.metadata.get(
                "semantic_learning_scope_fingerprint"
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
            checkpoint_semantic_state = checkpoint.metadata.get(
                "semantic_runtime_state_fingerprint"
            )
            if (
                checkpoint_semantic_state is None
                or payload.get(
                    "semantic_runtime_state_fingerprint"
                )
                != checkpoint_semantic_state
            ):
                continue
            checkpoint_topology_learning = checkpoint.metadata.get(
                "semantic_topology_learning_fingerprint"
            )
            if (
                checkpoint_topology_learning is None
                or payload.get(
                    "semantic_topology_learning_fingerprint"
                )
                != checkpoint_topology_learning
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