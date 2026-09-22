"""Adaptive execution harness for the advanced Jeeves stack.

``FrontierJeevesAgentRuntime`` is the hardened safety/control substrate. This
module subclasses it with adaptive inference-time compute and cross-run learning
hooks while preserving frontier tool authorization, audit binding, evidence,
verification, budgets, crash quarantine, and checkpoints.

The adaptive harness adds:

* dynamic compute allocation from measurable run state;
* specialist beam/adversarial search for difficult reasoning-only steps;
* run-scoped context-repository branches and checkpoint snapshots;
* normalized trajectory generation and causal credit assignment after runs;
* optional independent verification council diagnostics;
* experience retrieval for novelty estimates;
* bounded, content-addressed adaptive telemetry.

The model is never allowed to promote memory, tools, or policy changes through
this module.  Cross-run changes belong to the separate self-evolution control
plane.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from .adversarial_verification import CouncilVerdict, VerificationCouncil, VerificationSubject
from .context_repository import (
    ContextEntry,
    ContextKind,
    ContextNamespace,
    ContextPatch,
    ContextPatchItem,
    ContextRepository,
    PatchOperation,
)
from .deliberation import (
    CandidateProposal,
    CandidateScorer,
    ComputeAllocation,
    ComputeBudget,
    ComputeSignals,
    DeliberationEngine,
    DeliberationMode,
    DynamicComputeAllocator,
    SpecialistRole,
    proposal,
)
from .evidence import EvidenceLedger
from .frontier_adjudication import HostCandidateAdjudicator
from .frontier_consensus import merge_search_results
from .frontier_feedback import FrontierReasoningFeedback
from .frontier_probe_planning import FrontierProbePlanner
from .frontier_reasoning import (
    EscalationCause,
    FrontierReasoningCoordinator,
    InferenceDisposition,
)
from .frontier_runtime import FrontierJeevesAgentRuntime
from .runtime import (
    AgentResult,
    RunCheckpoint,
    RunInputs,
    RuntimeErrorBase,
    _RunState,
)
from .trajectory_learning import (
    CausalCreditAssigner,
    CreditReport,
    ExperienceQuery,
    ExperienceStore,
    Trajectory,
    TrajectoryBuilder,
)
from .types import (
    AgentPhase,
    ModelMessage,
    RiskTier,
    StepStatus,
    TerminationReason,
    bounded_text,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .verification import StepVerifier


class AdaptiveRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdaptiveConfig:
    enable_specialist_search: bool = True
    specialist_search_threshold: float = 0.60
    maximum_specialist_width: int = 6
    checkpoint_context_snapshots: bool = True
    checkpoint_snapshot_limit: int = 96
    trajectory_learning: bool = True
    verification_council: bool = True
    context_retrieval_entries: int = 8
    context_retrieval_tokens: int = 3000
    minimum_experience_similarity: float = 0.30
    retain_adaptive_reports: int = 2048
    enable_frontier_reasoning: bool = True
    enable_self_consistency: bool = True
    maximum_frontier_rounds: int = 2
    frontier_escalation_min_budget: float = 0.15
    minimum_frontier_uncertainty_reduction: float = 0.03
    fail_closed_on_evidence_gap: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "specialist_search_threshold", probability("specialist_search_threshold", self.specialist_search_threshold))
        for name in ("maximum_specialist_width", "checkpoint_snapshot_limit", "context_retrieval_entries", "context_retrieval_tokens", "retain_adaptive_reports", "maximum_frontier_rounds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive integer")
        object.__setattr__(self, "minimum_experience_similarity", probability("minimum_experience_similarity", self.minimum_experience_similarity))
        object.__setattr__(self, "frontier_escalation_min_budget", probability("frontier_escalation_min_budget", self.frontier_escalation_min_budget))
        object.__setattr__(
            self,
            "minimum_frontier_uncertainty_reduction",
            probability(
                "minimum_frontier_uncertainty_reduction",
                self.minimum_frontier_uncertainty_reduction,
            ),
        )


@dataclass(frozen=True, slots=True)
class AllocationRecord:
    sequence: int
    purpose: str
    allocation: ComputeAllocation
    signals: ComputeSignals
    requested_tokens: int
    granted_tokens: int
    at: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SpecialistSearchRecord:
    step_id: str
    mode: DeliberationMode
    selected_candidate_id: str | None
    candidate_count: int
    model_calls: int
    estimated_tokens: int
    stopped_reason: str
    trace_fingerprint: str
    frontier_decision_fingerprint: str | None = None
    frontier_disposition: str | None = None
    consensus_fingerprint: str | None = None
    escalation_rounds: int = 0
    frontier_stagnated: bool = False
    uncertainty_reduction: float = 0.0


@dataclass(frozen=True, slots=True)
class AdaptiveRunReport:
    run_id: str
    result_success: bool
    result_reason: str
    trajectory_id: str | None
    trajectory_fingerprint: str | None
    credit_fingerprint: str | None
    council_fingerprint: str | None
    allocation_count: int
    specialist_searches: tuple[SpecialistSearchRecord, ...]
    context_branch: str
    context_head: str | None
    experience_matches: int
    fingerprint: str


@dataclass(slots=True)
class _AdaptiveState:
    run_id: str
    context_branch: str
    allocations: list[AllocationRecord] = field(default_factory=list)
    searches: list[SpecialistSearchRecord] = field(default_factory=list)
    experience_matches: int = 0
    allocation_sequence: int = 0
    frontier_decision_fingerprints: list[str] = field(default_factory=list)


class AdaptiveJeevesRuntime(FrontierJeevesAgentRuntime):
    def __init__(
        self,
        *,
        compute_allocator: DynamicComputeAllocator | None = None,
        experience_store: ExperienceStore | None = None,
        trajectory_builder: TrajectoryBuilder | None = None,
        credit_assigner: CausalCreditAssigner | None = None,
        verification_council: VerificationCouncil | None = None,
        adaptive_config: AdaptiveConfig | None = None,
        frontier_reasoning: FrontierReasoningCoordinator | None = None,
        frontier_feedback: FrontierReasoningFeedback | None = None,
        frontier_probe_planner: FrontierProbePlanner | None = None,
        context_repository_factory: Callable[[ContextNamespace], ContextRepository] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.compute_allocator = compute_allocator or DynamicComputeAllocator()
        self.experiences = experience_store or ExperienceStore()
        self.trajectory_builder = trajectory_builder or TrajectoryBuilder(clock=self._wall_clock)
        self.credit_assigner = credit_assigner or CausalCreditAssigner()
        self.council = verification_council
        self.adaptive_config = adaptive_config or AdaptiveConfig()
        self.frontier_reasoning = frontier_reasoning or FrontierReasoningCoordinator()
        self.frontier_feedback = frontier_feedback or FrontierReasoningFeedback()
        self.frontier_probe_planner = frontier_probe_planner or FrontierProbePlanner()
        self._context_factory = context_repository_factory or (lambda namespace: ContextRepository(namespace, clock=self._wall_clock))
        self._context_repositories: dict[str, ContextRepository] = {}
        self._adaptive: dict[str, _AdaptiveState] = {}
        self._reports: dict[str, AdaptiveRunReport] = {}
        self._adaptive_lock = threading.RLock()

    def run(self, inputs: RunInputs) -> AgentResult:
        result = super().run(inputs)
        return self._post_run(inputs, result)

    def resume(self, inputs: RunInputs, run_id: str) -> AgentResult:
        result = super().resume(inputs, run_id)
        return self._post_run(inputs, result)

    def _new_state(self, run_id: str, inputs: RunInputs) -> _RunState:
        state = super()._new_state(run_id, inputs)
        repo = self._context_repo(inputs)
        branch = self._run_branch(run_id)
        if branch not in repo.branches():
            repo.branch(branch, from_branch="main")
        with self._adaptive_lock:
            self._adaptive[run_id] = _AdaptiveState(run_id=run_id, context_branch=branch)
        self._seed_run_context(repo, branch, inputs, run_id)
        return state

    def _state_from_checkpoint(self, inputs: RunInputs, checkpoint: RunCheckpoint) -> _RunState:
        state = super()._state_from_checkpoint(inputs, checkpoint)
        repo = self._context_repo(inputs)
        branch = self._run_branch(checkpoint.run_id)
        if branch not in repo.branches():
            repo.branch(branch, from_branch="main")
        with self._adaptive_lock:
            self._adaptive.setdefault(checkpoint.run_id, _AdaptiveState(checkpoint.run_id, branch))
        return state

    def _model_call(
        self,
        state: _RunState,
        *,
        messages: Sequence[Any],
        requested_max_tokens: int,
        tools: Sequence[Mapping[str, Any]] = (),
        response_schema: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        purpose = str(dict(metadata or {}).get("purpose") or "model")
        signals = self._compute_signals(state, purpose=purpose)
        remaining = self._global_budget_fraction_remaining(state)
        allocation = self.compute_allocator.allocate(signals, global_budget_fraction_remaining=remaining)
        if purpose.startswith("verification"):
            factor = 0.60 + allocation.expected_value * 0.40
        elif purpose in {"planning", "replanning"}:
            factor = 0.70 + allocation.expected_value * 0.30
        elif purpose.startswith("deliberation:"):
            factor = 1.0
        else:
            factor = 0.45 + allocation.expected_value * 0.55
        granted = max(256, min(requested_max_tokens, round(requested_max_tokens * factor), allocation.budget.max_tokens))
        self._record_allocation(state, purpose, allocation, signals, requested_max_tokens, granted)
        enriched = dict(metadata or {})
        enriched.update(
            {
                "adaptive_mode": allocation.mode.value,
                "adaptive_expected_value": allocation.expected_value,
                "adaptive_allocation": allocation.fingerprint,
            }
        )
        return super()._model_call(
            state,
            messages=messages,
            requested_max_tokens=granted,
            tools=tools,
            response_schema=response_schema,
            metadata=enriched,
        )

    def _execute_reasoning_step(self, state: _RunState, step) -> AgentResult | None:
        signals = self._compute_signals(state, purpose="reasoning-step", step=step)
        allocation = self.compute_allocator.allocate(
            signals,
            global_budget_fraction_remaining=self._global_budget_fraction_remaining(state),
        )
        if (
            not self.adaptive_config.enable_specialist_search
            or allocation.expected_value < self.adaptive_config.specialist_search_threshold
            or allocation.mode in {DeliberationMode.DIRECT, DeliberationMode.PLAN}
        ):
            return super()._execute_reasoning_step(state, step)

        task = self._specialist_task(state, step)
        generator = self._provider_specialist_generator(state)
        candidate_adjudicator = HostCandidateAdjudicator(state.ledger)
        candidate_scorer = CandidateScorer(verifier=candidate_adjudicator.score)
        engine = DeliberationEngine(
            generator,
            scorer=candidate_scorer,
            clock=self._monotonic,
        )
        search = engine.search(task, allocation)
        decision = (
            self.frontier_reasoning.decide(search, risk=step.risk)
            if self.adaptive_config.enable_frontier_reasoning
            else None
        )
        escalation_rounds = 0
        frontier_stagnated = False
        frontier_uncertainty_reduction = 0.0
        previous_uncertainty = (
            self._frontier_uncertainty(decision) if decision is not None else 0.0
        )

        while (
            decision is not None
            and self.adaptive_config.enable_self_consistency
            and decision.disposition is InferenceDisposition.DELIBERATE
            and escalation_rounds < self.adaptive_config.maximum_frontier_rounds
        ):
            escalated = self._frontier_escalation_allocation(
                state,
                allocation,
                decision,
                escalation_rounds,
            )
            if escalated is None:
                break
            extra = DeliberationEngine(
                generator,
                scorer=candidate_scorer,
                clock=self._monotonic,
            ).search(task, escalated)
            search = merge_search_results(search, extra)
            escalation_rounds += 1
            decision = self.frontier_reasoning.decide(search, risk=step.risk)
            current_uncertainty = self._frontier_uncertainty(decision)
            frontier_uncertainty_reduction = max(
                0.0,
                previous_uncertainty - current_uncertainty,
            )
            if (
                decision.disposition is InferenceDisposition.DELIBERATE
                and frontier_uncertainty_reduction
                < self.adaptive_config.minimum_frontier_uncertainty_reduction
            ):
                frontier_stagnated = True
                state.trace.emit(
                    "frontier.escalation_stagnated",
                    {
                        "step_id": step.step_id,
                        "round": escalation_rounds,
                        "previous_uncertainty": previous_uncertainty,
                        "current_uncertainty": current_uncertainty,
                        "uncertainty_reduction": frontier_uncertainty_reduction,
                        "minimum_reduction": self.adaptive_config.minimum_frontier_uncertainty_reduction,
                        "decision": decision.fingerprint,
                    },
                )
                self.metrics.increment("agent.frontier.escalation_stagnated")
                break
            previous_uncertainty = current_uncertainty

        adaptive = self._adaptive_state(state.run_id)
        if decision is not None:
            adaptive.frontier_decision_fingerprints.append(decision.fingerprint)
        adaptive.searches.append(
            SpecialistSearchRecord(
                step_id=step.step_id,
                mode=search.mode,
                selected_candidate_id=(
                    decision.leading_candidate.candidate_id
                    if decision is not None and decision.leading_candidate is not None
                    else search.best.candidate_id if search.best else None
                ),
                candidate_count=len(search.explored),
                model_calls=int(search.ledger.get("model_calls", 0)),
                estimated_tokens=int(search.ledger.get("estimated_tokens", 0)),
                stopped_reason=search.stopped_reason,
                trace_fingerprint=search.trace_fingerprint,
                frontier_decision_fingerprint=decision.fingerprint if decision else None,
                frontier_disposition=decision.disposition.value if decision else None,
                consensus_fingerprint=(
                    decision.consensus.fingerprint
                    if decision is not None and decision.consensus is not None
                    else None
                ),
                escalation_rounds=escalation_rounds,
                frontier_stagnated=frontier_stagnated,
                uncertainty_reduction=frontier_uncertainty_reduction,
            )
        )
        state.trace.emit(
            "deliberation.completed",
            {
                "step_id": step.step_id,
                "mode": search.mode.value,
                "candidate_count": len(search.explored),
                "selected": (
                    decision.leading_candidate.candidate_id
                    if decision is not None and decision.leading_candidate is not None
                    else search.best.candidate_id if search.best else None
                ),
                "search_trace": search.trace_fingerprint,
                "frontier_disposition": decision.disposition.value if decision else None,
                "frontier_causes": [cause.value for cause in decision.causes] if decision else [],
                "consensus_agreement": (
                    decision.consensus.agreement
                    if decision is not None and decision.consensus is not None
                    else None
                ),
                "escalation_rounds": escalation_rounds,
                "frontier_stagnated": frontier_stagnated,
                "uncertainty_reduction": frontier_uncertainty_reduction,
            },
        )

        if search.best is None:
            return super()._execute_reasoning_step(state, step)

        if decision is not None and decision.disposition not in {
            InferenceDisposition.COMMIT,
            InferenceDisposition.VERIFY,
        }:
            reason = self._frontier_block_reason(decision)
            probe_plan = None
            try:
                probe_plan = self.frontier_probe_planner.plan(decision)
            except Exception as exc:
                state.trace.emit(
                    "frontier.probe_planning_failed",
                    {
                        "step_id": step.step_id,
                        "decision": decision.fingerprint,
                        "error": f"{type(exc).__name__}: {str(exc)[:512]}",
                    },
                )
                self.metrics.increment("agent.frontier.probe_planning_failures")
            if probe_plan is not None:
                selected_probe = probe_plan.selected_probe
                state.trace.emit(
                    "frontier.probes_planned",
                    {
                        "step_id": step.step_id,
                        "decision": decision.fingerprint,
                        "plan": probe_plan.fingerprint,
                        "gaps": [gap.gap_id for gap in probe_plan.gaps],
                        "probes": [probe.probe_id for probe in probe_plan.probes],
                        "selected_probe": (
                            selected_probe.probe_id if selected_probe is not None else None
                        ),
                        "selected_kind": (
                            selected_probe.kind.value if selected_probe is not None else None
                        ),
                    },
                )
                self.metrics.increment("agent.frontier.probes_planned")
            state.scratch.set(
                f"frontier:block:{step.step_id}",
                {
                    "decision": decision.fingerprint,
                    "disposition": decision.disposition.value,
                    "causes": [cause.value for cause in decision.causes],
                    "consensus": decision.consensus.fingerprint if decision.consensus else None,
                    "reason": reason,
                    "probe_plan": probe_plan.as_json() if probe_plan is not None else None,
                },
                importance=0.95,
            )
            if (
                decision.disposition is InferenceDisposition.SEEK_EVIDENCE
                and not self.adaptive_config.fail_closed_on_evidence_gap
            ):
                return super()._execute_reasoning_step(state, step)
            assert state.plan is not None
            retryable = decision.disposition is InferenceDisposition.DELIBERATE
            state.plan = self.scheduler.fail(
                state.plan,
                step.step_id,
                retryable=retryable,
            )
            state.last_error = reason[:8192]
            state.trace.emit(
                "frontier.reasoning_blocked",
                {
                    "step_id": step.step_id,
                    "decision": decision.fingerprint,
                    "disposition": decision.disposition.value,
                    "causes": [cause.value for cause in decision.causes],
                    "retryable": retryable,
                },
            )
            self.metrics.increment("agent.frontier.reasoning_blocked")
            if retryable and state.plan.step(step.step_id).status is not StepStatus.FAILED:
                self.metrics.increment("agent.frontier.reasoning_retries")
                self._checkpoint(state)
                return None
            if self._attempt_replan(state, reason, failed_step_id=step.step_id):
                return None
            return self._finish_failure(
                state,
                TerminationReason.VERIFICATION_FAILED,
                reason,
                metadata={
                    "step_id": step.step_id,
                    "frontier_decision": decision.fingerprint,
                    "frontier_disposition": decision.disposition.value,
                },
            )

        if decision is not None and decision.disposition is InferenceDisposition.VERIFY:
            state.trace.emit(
                "frontier.verification_required",
                {
                    "step_id": step.step_id,
                    "decision": decision.fingerprint,
                    "causes": [cause.value for cause in decision.causes],
                    "verification": "step_verifier",
                },
            )
            self.metrics.increment("agent.frontier.verification_required")

        selected = (
            decision.leading_candidate
            if decision is not None and decision.leading_candidate is not None
            else search.best
        )
        assert selected is not None
        state.scratch.set(
            f"analysis:{step.step_id}",
            {
                "summary": selected.summary,
                "proposed_action": selected.proposed_action,
                "predicted_outcome": selected.predicted_outcome,
                "confidence": selected.confidence,
                "evidence_ids": [ref.evidence_id for ref in selected.evidence],
                "assumptions": list(selected.assumptions),
                "risks": list(selected.risks),
                "search_trace": search.trace_fingerprint,
                "frontier_decision": decision.fingerprint if decision else None,
                "frontier_disposition": decision.disposition.value if decision else None,
                "consensus": decision.consensus.fingerprint if decision and decision.consensus else None,
                "escalation_rounds": escalation_rounds,
            },
            importance=0.90,
        )
        self._remember_working(
            state.inputs.namespace,
            selected.summary,
            source="specialist-deliberation",
            tags=("analysis", "deliberation", step.step_id, state.run_id),
            trust=min(0.60, selected.confidence),
            salience=0.65,
            evidence=selected.evidence,
        )
        verifier = StepVerifier(
            state.ledger,
            policy=self.verification_policy,
            clock=self._wall_clock,
        )
        self._transition(state, AgentPhase.VERIFYING)
        report = verifier.verify(step)
        state.last_verification = report
        if decision is not None:
            self.frontier_feedback.observe(
                decision,
                verified_success=report.passed,
                escalation_rounds=escalation_rounds,
                model_calls=int(search.ledger.get("model_calls", 0)),
                estimated_tokens=int(search.ledger.get("estimated_tokens", 0)),
            )
        if report.passed:
            assert state.plan is not None
            state.plan = self.scheduler.succeed(state.plan, step.step_id)
            state.trace.emit(
                "step.succeeded",
                {
                    **self._verification_event(report),
                    "frontier_decision": decision.fingerprint if decision else None,
                    "frontier_feedback": self.frontier_feedback.report().fingerprint,
                },
            )
            self.metrics.increment("agent.steps.succeeded")
            self._checkpoint(state)
            return None
        return self._handle_step_failure(state, step, report, tool_failed=False)

    def _frontier_escalation_allocation(
        self,
        state: _RunState,
        allocation: ComputeAllocation,
        decision,
        round_index: int,
    ) -> ComputeAllocation | None:
        remaining_fraction = self._global_budget_fraction_remaining(state)
        if remaining_fraction < self.adaptive_config.frontier_escalation_min_budget:
            return None
        budget = state.inputs.budget
        elapsed = max(0.0, self._monotonic() - state.started_monotonic)
        remaining_calls = max(0, budget.max_model_calls - state.usage.model_calls)
        remaining_tokens = max(0, budget.max_tokens - state.usage.total_tokens)
        remaining_wall = max(0.0, budget.max_wall_seconds - elapsed)
        if remaining_calls < 1 or remaining_tokens < 512 or remaining_wall < 3.0:
            return None

        causes = set(decision.causes)
        mode = (
            DeliberationMode.COUNTERFACTUAL
            if EscalationCause.OUTCOME_DISAGREEMENT in causes
            else DeliberationMode.ADVERSARIAL
        )
        local = allocation.budget
        search_budget = ComputeBudget(
            max_model_calls=max(1, min(remaining_calls, max(2, min(8, local.max_model_calls + 2)))),
            max_candidates=max(2, min(64, max(local.max_candidates, local.beam_width * 4))),
            max_depth=max(2, min(6, local.max_depth + 1)),
            max_tokens=max(512, min(remaining_tokens, max(2_048, local.max_tokens))),
            max_wall_seconds=max(3.0, min(remaining_wall, max(10.0, local.max_wall_seconds))),
            beam_width=max(2, min(self.adaptive_config.maximum_specialist_width, local.beam_width + 1)),
            adversarial_rounds=max(1, min(4, local.adversarial_rounds + 1)),
        )
        expected_value = min(
            1.0,
            allocation.expected_value + 0.10 + 0.05 * round_index,
        )
        rationale = tuple(allocation.rationale) + (
            f"frontier escalation round={round_index + 1}",
            f"frontier disposition={decision.disposition.value}",
            "frontier causes=" + ",".join(cause.value for cause in decision.causes),
        )
        return ComputeAllocation(
            mode=mode,
            budget=search_budget,
            expected_value=expected_value,
            rationale=rationale,
            fingerprint=stable_fingerprint(
                {
                    "parent": allocation.fingerprint,
                    "round": round_index + 1,
                    "mode": mode.value,
                    "decision": decision.fingerprint,
                    "budget": {
                        "calls": search_budget.max_model_calls,
                        "candidates": search_budget.max_candidates,
                        "depth": search_budget.max_depth,
                        "tokens": search_budget.max_tokens,
                        "wall": search_budget.max_wall_seconds,
                        "beam": search_budget.beam_width,
                        "adversarial_rounds": search_budget.adversarial_rounds,
                    },
                }
            ),
        )

    @staticmethod
    def _frontier_uncertainty(decision) -> float:
        if decision is None:
            return 0.0
        values = [
            decision.diagnostics.normalized_entropy,
            decision.diagnostics.action_disagreement,
            decision.diagnostics.outcome_disagreement,
        ]
        if decision.consensus is not None:
            values.append(decision.consensus.normalized_entropy)
            values.append(1.0 - decision.consensus.agreement)
        return max(0.0, min(1.0, max(values, default=0.0)))

    @staticmethod
    def _frontier_block_reason(decision) -> str:
        causes = ", ".join(cause.value for cause in decision.causes) or "unresolved frontier uncertainty"
        if decision.disposition is InferenceDisposition.SEEK_EVIDENCE:
            return "Frontier reasoning requires additional factual evidence before this step can be accepted: " + causes
        if decision.disposition is InferenceDisposition.ABSTAIN:
            return "Frontier reasoning abstained because the candidate set could not be justified: " + causes
        return "Frontier reasoning remained unresolved after bounded extra inference: " + causes

    def _checkpoint(self, state: _RunState) -> RunCheckpoint:
        checkpoint = super()._checkpoint(state)
        if self.adaptive_config.checkpoint_context_snapshots and checkpoint.sequence <= self.adaptive_config.checkpoint_snapshot_limit:
            try:
                self._snapshot_checkpoint_context(state, checkpoint)
            except Exception as exc:
                state.trace.emit(
                    "adaptive.context_snapshot_failed",
                    {"checkpoint": checkpoint.sequence, "error": f"{type(exc).__name__}: {str(exc)[:512]}"},
                )
                self.metrics.increment("agent.adaptive.context_snapshot_failures")
        return checkpoint

    def report(self, run_id: str) -> AdaptiveRunReport | None:
        run_id = require_id("run_id", run_id)
        with self._adaptive_lock:
            return self._reports.get(run_id)

    def context_repository(self, inputs: RunInputs) -> ContextRepository:
        return self._context_repo(inputs)

    def _post_run(self, inputs: RunInputs, result: AgentResult) -> AgentResult:
        trajectory: Trajectory | None = None
        credit: CreditReport | None = None
        council: CouncilVerdict | None = None
        if self.adaptive_config.trajectory_learning:
            try:
                checkpoints = self.checkpointer.history(result.run_id)
                trajectory = self.trajectory_builder.build(result, checkpoints=checkpoints, metadata={"runtime": "adaptive"})
                self.experiences.put(trajectory)
                credit = self.credit_assigner.assign(trajectory)
            except Exception:
                self.metrics.increment("agent.adaptive.trajectory_failures")
        if self.adaptive_config.verification_council and self.council is not None:
            try:
                ledger = EvidenceLedger(clock=self._wall_clock)
                latest = self.checkpointer.latest(result.run_id)
                if latest is not None:
                    for artifact in latest.evidence:
                        ledger.append(artifact)
                subject = VerificationSubject(
                    subject_id=stable_id("subject", {"run": result.run_id, "trace": result.trace_fingerprint}),
                    answer=result.answer,
                    claims=result.claims,
                    required_criteria=inputs.goal.success_criteria,
                    risk=self._maximum_plan_risk(result.plan),
                    context={"run_id": result.run_id, "termination": result.reason.value},
                )
                council = self.council.evaluate(subject, ledger)
            except Exception:
                self.metrics.increment("agent.adaptive.council_failures")
        repo = self._context_repo(inputs)
        adaptive = self._adaptive_state(result.run_id)
        try:
            self._stage_run_summary(repo, adaptive.context_branch, inputs, result, trajectory, credit, council)
        except Exception:
            self.metrics.increment("agent.adaptive.summary_failures")
        feedback_report = self.frontier_feedback.report()
        feedback_recommendation = self.frontier_feedback.recommendation()
        report_payload = {
            "run": result.run_id,
            "success": result.success,
            "reason": result.reason.value,
            "trajectory": trajectory.fingerprint if trajectory else None,
            "credit": credit.fingerprint if credit else None,
            "council": council.fingerprint if council else None,
            "allocations": [record.fingerprint for record in adaptive.allocations],
            "searches": [record.trace_fingerprint for record in adaptive.searches],
            "context_head": repo.head(adaptive.context_branch),
            "experience_matches": adaptive.experience_matches,
            "frontier_decisions": list(adaptive.frontier_decision_fingerprints),
            "frontier_feedback": feedback_report.fingerprint,
            "frontier_feedback_recommendation": feedback_recommendation.fingerprint,
        }
        report = AdaptiveRunReport(
            run_id=result.run_id,
            result_success=result.success,
            result_reason=result.reason.value,
            trajectory_id=trajectory.trajectory_id if trajectory else None,
            trajectory_fingerprint=trajectory.fingerprint if trajectory else None,
            credit_fingerprint=credit.fingerprint if credit else None,
            council_fingerprint=council.fingerprint if council else None,
            allocation_count=len(adaptive.allocations),
            specialist_searches=tuple(adaptive.searches),
            context_branch=adaptive.context_branch,
            context_head=repo.head(adaptive.context_branch),
            experience_matches=adaptive.experience_matches,
            fingerprint=stable_fingerprint(report_payload),
        )
        with self._adaptive_lock:
            self._reports[result.run_id] = report
            if len(self._reports) > self.adaptive_config.retain_adaptive_reports:
                oldest = next(iter(self._reports))
                self._reports.pop(oldest, None)
        metadata = dict(result.metadata)
        metadata["adaptive"] = {
            "report_fingerprint": report.fingerprint,
            "trajectory_id": report.trajectory_id,
            "credit_fingerprint": report.credit_fingerprint,
            "council_verdict": council.verdict.value if council else None,
            "council_score": council.score if council else None,
            "context_branch": report.context_branch,
            "context_head": report.context_head,
            "allocation_count": report.allocation_count,
            "specialist_searches": len(report.specialist_searches),
            "frontier_decisions": len(adaptive.frontier_decision_fingerprints),
            "frontier_feedback": {
                "fingerprint": feedback_report.fingerprint,
                "count": feedback_report.count,
                "commit_success_rate": feedback_report.commit_success_rate,
                "direct_success_rate": feedback_report.direct_success_rate,
                "escalated_success_rate": feedback_report.escalated_success_rate,
                "observed_escalation_delta": feedback_report.observed_escalation_delta,
                "brier_score": feedback_report.brier_score,
                "calibration_gap": feedback_report.calibration_gap,
            },
            "frontier_feedback_recommendation": {
                "fingerprint": feedback_recommendation.fingerprint,
                "minimum_quality_delta": feedback_recommendation.minimum_quality_delta,
                "minimum_choice_probability_delta": feedback_recommendation.minimum_choice_probability_delta,
                "maximum_entropy_delta": feedback_recommendation.maximum_entropy_delta,
                "reasons": list(feedback_recommendation.reasons),
            },
        }
        return replace(result, metadata=json_safe(metadata))

    def _compute_signals(self, state: _RunState, *, purpose: str, step=None) -> ComputeSignals:
        plan = state.plan
        plan_size = len(plan.steps) if plan is not None else 1
        dependency_count = sum(len(value.dependencies) for value in plan.steps) if plan is not None else 0
        complexity = min(1.0, 0.18 + math.log2(plan_size + 1) / 8.0 + min(0.25, dependency_count / 40.0))
        artifacts = state.ledger.artifacts()
        if artifacts:
            mean_confidence = sum(value.confidence for value in artifacts) / len(artifacts)
            uncertainty = 1.0 - mean_confidence * 0.70
        else:
            uncertainty = 0.78
        if step is not None and getattr(step, "attempts", 0):
            uncertainty = min(1.0, uncertainty + min(0.20, step.attempts * 0.05))
        evidence_ids = [value.evidence_id for value in artifacts]
        contradictions = state.ledger.contradictions_for(evidence_ids) if evidence_ids else ()
        contradiction = min(1.0, len(contradictions) / max(1, len(artifacts)))
        failure_count = sum(1 for value in state.observations if not value.ok)
        if state.last_verification is not None and not state.last_verification.passed:
            failure_count += 1
        failure_pressure = min(1.0, failure_count / 4.0)
        novelty, matches = self._experience_novelty(state)
        adaptive = self._adaptive_state(state.run_id)
        adaptive.experience_matches = max(adaptive.experience_matches, matches)
        expected_information_gain = min(1.0, uncertainty * (0.65 if not artifacts else 0.35) + contradiction * 0.35)
        risk = step.risk if step is not None else self._current_risk(plan)
        scratch_entries = len(state.scratch.entries())
        context_saturation = min(1.0, scratch_entries / 64.0 + state.usage.total_tokens / max(1, state.inputs.budget.max_tokens) * 0.35)
        elapsed = max(0.0, self._monotonic() - state.started_monotonic)
        deadline_pressure = min(1.0, elapsed / max(1e-9, state.inputs.budget.max_wall_seconds))
        # Until empirical skill profiles are directly attached to this harness,
        # use recent success of matching trajectories as a conservative proxy.
        skill_reliability = 0.5
        if matches:
            query = self._experience_query(state)
            hits = self.experiences.search(query)
            skill_reliability = sum(1.0 if hit.trajectory.success else 0.0 for hit in hits) / len(hits) if hits else 0.5
        return ComputeSignals(
            complexity=complexity,
            uncertainty=max(0.0, min(1.0, uncertainty)),
            novelty=novelty,
            contradiction=contradiction,
            expected_information_gain=expected_information_gain,
            failure_pressure=failure_pressure,
            risk=risk,
            context_saturation=context_saturation,
            empirical_skill_reliability=skill_reliability,
            deadline_pressure=deadline_pressure,
        )

    def _provider_specialist_generator(self, state: _RunState):
        def generate(task: str, parent: CandidateProposal | None, role: SpecialistRole, width: int) -> Sequence[CandidateProposal]:
            width = max(1, min(width, self.adaptive_config.maximum_specialist_width))
            parent_context = None
            if parent is not None:
                parent_context = {
                    "summary": parent.summary,
                    "action": parent.proposed_action,
                    "outcome": parent.predicted_outcome,
                    "assumptions": list(parent.assumptions),
                    "risks": list(parent.risks),
                }
            instruction = (
                "Produce concise candidate decision summaries for a host-controlled agent. "
                "Do not expose private chain-of-thought. Return JSON only with key 'candidates'. "
                "Each candidate must include summary, proposed_action, predicted_outcome, confidence, "
                "evidence_ids, assumptions, risks, expected_cost, expected_latency_ms. "
                f"Specialist role: {role.value}. Number of candidates: {width}."
            )
            user_payload = json.dumps({"task": task, "parent": parent_context}, ensure_ascii=False, sort_keys=True)
            response = self._model_call(
                state,
                messages=(ModelMessage("system", instruction), ModelMessage("user", user_payload)),
                requested_max_tokens=min(4096, max(1024, width * 700)),
                response_schema={
                    "type": "object",
                    "required": ["candidates"],
                    "properties": {"candidates": {"type": "array"}},
                },
                metadata={"purpose": f"deliberation:{role.value}", "width": width},
            )
            try:
                payload = json.loads(response.content)
            except json.JSONDecodeError as exc:
                raise AdaptiveRuntimeError("specialist returned invalid JSON") from exc
            raw_candidates = payload.get("candidates") if isinstance(payload, dict) else None
            if not isinstance(raw_candidates, list):
                raise AdaptiveRuntimeError("specialist response missing candidates array")
            values: list[CandidateProposal] = []
            for raw in raw_candidates[:width]:
                if not isinstance(raw, dict):
                    continue
                evidence_ids = raw.get("evidence_ids", [])
                refs = []
                if isinstance(evidence_ids, list):
                    for evidence_id in evidence_ids:
                        if isinstance(evidence_id, str):
                            artifact = state.ledger.get(evidence_id)
                            if artifact is not None:
                                refs.append(artifact.ref)
                values.append(
                    proposal(
                        role=role,
                        summary=str(raw.get("summary", "Candidate summary unavailable.")),
                        proposed_action=str(raw.get("proposed_action", "Continue bounded reasoning.")),
                        predicted_outcome=str(raw.get("predicted_outcome", "Unknown outcome.")),
                        confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.5)))),
                        parent=parent,
                        evidence=refs,
                        assumptions=tuple(str(value) for value in raw.get("assumptions", []) if isinstance(value, str)) if isinstance(raw.get("assumptions", []), list) else (),
                        risks=tuple(str(value) for value in raw.get("risks", []) if isinstance(value, str)) if isinstance(raw.get("risks", []), list) else (),
                        expected_cost=max(0.0, float(raw.get("expected_cost", 0.0))),
                        expected_latency_ms=max(0.0, float(raw.get("expected_latency_ms", 0.0))),
                        metadata={"provider": response.provider, "model": response.model, "request_id": response.request_id},
                    )
                )
            return tuple(values)

        return generate

    def _specialist_task(self, state: _RunState, step) -> str:
        context = self._context_repo(state.inputs).retrieve(
            state.inputs.goal.objective + " " + step.description,
            branch=self._adaptive_state(state.run_id).context_branch,
            max_entries=self.adaptive_config.context_retrieval_entries,
            max_tokens=self.adaptive_config.context_retrieval_tokens,
            minimum_trust=0.0,
            include_unpromoted=True,
            touch=False,
        )
        context_payload = [
            {"key": hit.entry.key, "kind": hit.entry.kind.value, "content": hit.entry.content, "trust": hit.entry.trust, "confidence": hit.entry.confidence}
            for hit in context
        ]
        payload = {
            "goal": state.inputs.goal.objective,
            "success_criteria": list(state.inputs.goal.success_criteria),
            "constraints": list(state.inputs.goal.constraints),
            "step": {
                "id": step.step_id,
                "title": step.title,
                "description": step.description,
                "expected_outcome": step.expected_outcome,
                "verification": step.verification,
                "risk": step.risk.value,
            },
            "context": context_payload,
            "evidence": [
                {"id": artifact.evidence_id, "source": artifact.source, "confidence": artifact.confidence, "fingerprint": artifact.fingerprint}
                for artifact in state.ledger.artifacts()[-32:]
            ],
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _record_allocation(self, state: _RunState, purpose: str, allocation: ComputeAllocation, signals: ComputeSignals, requested: int, granted: int) -> None:
        adaptive = self._adaptive_state(state.run_id)
        adaptive.allocation_sequence += 1
        payload = {
            "run": state.run_id,
            "sequence": adaptive.allocation_sequence,
            "purpose": purpose,
            "allocation": allocation.fingerprint,
            "requested": requested,
            "granted": granted,
        }
        adaptive.allocations.append(
            AllocationRecord(
                adaptive.allocation_sequence,
                purpose[:128],
                allocation,
                signals,
                requested,
                granted,
                self._wall_clock(),
                stable_fingerprint(payload),
            )
        )

    def _global_budget_fraction_remaining(self, state: _RunState) -> float:
        budget = state.inputs.budget
        elapsed = max(0.0, self._monotonic() - state.started_monotonic)
        fractions = (
            1.0 - state.usage.steps / budget.max_steps,
            1.0 - state.usage.model_calls / budget.max_model_calls,
            1.0 - state.usage.tool_calls / budget.max_tool_calls,
            1.0 - state.usage.total_tokens / budget.max_tokens,
            1.0 - elapsed / budget.max_wall_seconds,
        )
        return max(0.0, min(1.0, min(fractions)))

    def _experience_query(self, state: _RunState) -> ExperienceQuery:
        tokens = tuple(token.casefold() for token in state.inputs.goal.objective.replace("/", " ").replace("_", " ").split() if token)
        tools = tuple(sorted({step.tool for step in state.plan.steps if step.tool})) if state.plan is not None else ()
        return ExperienceQuery(goal_tokens=tokens[:32], tools=tools, minimum_similarity=self.adaptive_config.minimum_experience_similarity, limit=8)

    def _experience_novelty(self, state: _RunState) -> tuple[float, int]:
        hits = self.experiences.search(self._experience_query(state))
        if not hits:
            return 0.90, 0
        best = hits[0].similarity
        return max(0.05, min(1.0, 1.0 - best)), len(hits)

    def _context_repo(self, inputs: RunInputs) -> ContextRepository:
        namespace = ContextNamespace(inputs.tenant_id, inputs.user_id, inputs.workspace_id)
        with self._adaptive_lock:
            repo = self._context_repositories.get(namespace.key)
            if repo is None:
                repo = self._context_factory(namespace)
                self._context_repositories[namespace.key] = repo
            return repo

    @staticmethod
    def _run_branch(run_id: str) -> str:
        return require_id("branch", f"run:{stable_fingerprint(run_id)[:24]}")

    def _seed_run_context(self, repo: ContextRepository, branch: str, inputs: RunInputs, run_id: str) -> None:
        now = self._wall_clock()
        entry = ContextEntry(
            entry_id=stable_id("ctx", {"run": run_id, "key": "goal"}),
            namespace=repo.namespace,
            key=stable_id("goalctx", {"run": run_id}),
            kind=ContextKind.SCRATCH,
            content=json.dumps({"goal": inputs.goal.objective, "success_criteria": inputs.goal.success_criteria, "constraints": inputs.goal.constraints}, ensure_ascii=False, sort_keys=True),
            created_at=now,
            updated_at=now,
            confidence=1.0,
            salience=0.95,
            trust=1.0,
            source="adaptive-runtime",
            tags=("run", "goal"),
            protected=False,
            promoted=False,
            metadata={"run_id": run_id},
        )
        patch = ContextPatch(
            patch_id=stable_id("ctxpatch", {"run": run_id, "seed": entry.content_fingerprint}),
            namespace=repo.namespace,
            items=(ContextPatchItem(PatchOperation.UPSERT, entry.key, entry=entry, reason="seed run goal"),),
            author="adaptive-runtime",
            created_at=now,
            rationale="initialize run-scoped context branch",
            source_run_id=run_id,
        )
        repo.commit(branch, patch, message="seed adaptive run context", expected_head=repo.head(branch))

    def _snapshot_checkpoint_context(self, state: _RunState, checkpoint: RunCheckpoint) -> None:
        repo = self._context_repo(state.inputs)
        branch = self._adaptive_state(state.run_id).context_branch
        now = self._wall_clock()
        key = stable_id("checkpointctx", {"run": state.run_id, "sequence": checkpoint.sequence})
        entry = ContextEntry(
            entry_id=stable_id("ctx", {"key": key, "checkpoint": checkpoint.fingerprint}),
            namespace=repo.namespace,
            key=key,
            kind=ContextKind.SCRATCH,
            content=json.dumps(
                {
                    "sequence": checkpoint.sequence,
                    "phase": checkpoint.phase.value,
                    "usage": {"steps": checkpoint.usage.steps, "model_calls": checkpoint.usage.model_calls, "tool_calls": checkpoint.usage.tool_calls, "tokens": checkpoint.usage.total_tokens},
                    "plan": checkpoint.plan.to_dict() if checkpoint.plan else None,
                    "observation_count": len(checkpoint.observations),
                    "evidence_count": len(checkpoint.evidence),
                    "replans": checkpoint.replan_count,
                    "last_error": checkpoint.last_error,
                    "trace": checkpoint.current_trace_fingerprint,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
            updated_at=now,
            confidence=1.0,
            salience=0.25,
            trust=1.0,
            source="checkpoint",
            tags=("checkpoint", checkpoint.phase.value),
            expires_at=now + 7 * 24 * 3600,
            metadata={"run_id": state.run_id, "sequence": checkpoint.sequence},
        )
        patch = ContextPatch(
            patch_id=stable_id("ctxpatch", {"run": state.run_id, "checkpoint": checkpoint.sequence, "entry": entry.content_fingerprint}),
            namespace=repo.namespace,
            items=(ContextPatchItem(PatchOperation.UPSERT, key, entry=entry, reason="snapshot checkpoint"),),
            author="adaptive-runtime",
            created_at=now,
            rationale="append run checkpoint to cognitive context branch",
            source_run_id=state.run_id,
        )
        repo.commit(branch, patch, message=f"checkpoint {checkpoint.sequence}", expected_head=repo.head(branch))

    def _stage_run_summary(self, repo: ContextRepository, branch: str, inputs: RunInputs, result: AgentResult, trajectory: Trajectory | None, credit: CreditReport | None, council: CouncilVerdict | None) -> None:
        now = self._wall_clock()
        key = stable_id("episode", {"run": result.run_id})
        entry = ContextEntry(
            entry_id=stable_id("ctx", {"episode": result.run_id, "trace": result.trace_fingerprint}),
            namespace=repo.namespace,
            key=key,
            kind=ContextKind.EPISODIC,
            content=json.dumps(
                {
                    "goal": inputs.goal.objective,
                    "success": result.success,
                    "reason": result.reason.value,
                    "answer_fingerprint": stable_fingerprint(result.answer),
                    "usage": {"steps": result.usage.steps, "model_calls": result.usage.model_calls, "tool_calls": result.usage.tool_calls, "tokens": result.usage.total_tokens},
                    "trajectory": trajectory.trajectory_id if trajectory else None,
                    "trajectory_fingerprint": trajectory.fingerprint if trajectory else None,
                    "credit_fingerprint": credit.fingerprint if credit else None,
                    "council": {"verdict": council.verdict.value, "score": council.score, "fingerprint": council.fingerprint} if council else None,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
            updated_at=now,
            confidence=0.95 if result.success else 0.85,
            salience=0.75,
            trust=1.0,
            source="adaptive-runtime",
            tags=("episode", "success" if result.success else "failure", result.reason.value),
            promoted=False,
            metadata={"run_id": result.run_id, "trace": result.trace_fingerprint},
        )
        patch = ContextPatch(
            patch_id=stable_id("ctxpatch", {"episode": result.run_id, "entry": entry.content_fingerprint}),
            namespace=repo.namespace,
            items=(ContextPatchItem(PatchOperation.UPSERT, key, entry=entry, reason="stage run episode"),),
            author="adaptive-runtime",
            created_at=now,
            rationale="persist audited run episode on run branch",
            source_run_id=result.run_id,
        )
        repo.commit(branch, patch, message="stage adaptive run episode", expected_head=repo.head(branch))

    def _adaptive_state(self, run_id: str) -> _AdaptiveState:
        run_id = require_id("run_id", run_id)
        with self._adaptive_lock:
            value = self._adaptive.get(run_id)
            if value is None:
                raise AdaptiveRuntimeError(f"missing adaptive state for run {run_id}")
            return value

    @staticmethod
    def _current_risk(plan) -> RiskTier:
        if plan is None:
            return RiskTier.READ_ONLY
        order = {RiskTier.READ_ONLY: 0, RiskTier.REVERSIBLE: 1, RiskTier.MUTATING: 2, RiskTier.EXTERNAL: 3, RiskTier.HIGH_IMPACT: 4}
        ready = plan.ready_steps()
        values = [step.risk for step in ready] or [step.risk for step in plan.steps]
        return max(values, key=lambda value: order[value], default=RiskTier.READ_ONLY)

    @staticmethod
    def _maximum_plan_risk(plan) -> RiskTier:
        return AdaptiveJeevesRuntime._current_risk(plan)


# Explicit public name for callers that want adaptive inference while retaining
# the hardened frontier execution substrate.
FrontierAdaptiveJeevesRuntime = AdaptiveJeevesRuntime
