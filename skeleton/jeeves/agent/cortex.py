"""High-level cognitive architecture for advanced Jeeves runs.

``JeevesCortex`` composes the evidence-first runtime with three deeper layers:

* a per-run rollbackable world/belief graph;
* a cross-run empirical skill/action library learned only from verified output;
* a deterministic metacognitive controller that chooses the next cognitive mode.

The cortex never executes tools directly and never grants capabilities.  It
produces recommendations, state summaries, learned priors, information-gain
questions, and post-run updates.  The existing runtime remains the authority
for policy, tool execution, evidence custody, verification, and checkpoints.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from .action_model import (
    ContextSignature,
    SkillLibrary,
    SkillScore,
    SkillSelection,
    SkillSpec,
)
from .evidence import EvidenceArtifact, EvidenceLedger
from .metacognition import (
    CognitiveMode,
    LoopDetector,
    LoopSignals,
    MetaController,
    MetaDecision,
    MetaPolicy,
    MetaState,
    MetaStateBuilder,
    RiskSignals,
)
from .runtime import RunCheckpoint, RunInputs
from .types import (
    AgentContractError,
    AgentPhase,
    AgentResult,
    Claim,
    EvidenceKind,
    Plan,
    RiskTier,
    ToolObservation,
    bounded_text,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .world_model import (
    BeliefGraph,
    BeliefState,
    BeliefUpdate,
    CounterfactualProbe,
    EdgeKind,
    Hypothesis,
    Proposition,
    WorldModel,
    WorldModelError,
)


class CortexError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CortexConfig:
    scope_prefix: str = "run"
    belief_prior: float = 0.50
    verified_observation_reliability: float = 0.92
    failed_observation_reliability: float = 0.82
    claim_prior: float = 0.50
    max_probe_count: int = 8
    checkpoint_history: int = 128
    decision_history: int = 256
    learn_from_failed_runs: bool = True
    learn_read_only_actions: bool = True
    preserve_run_worlds: bool = True
    stale_evidence_seconds: float = 24 * 3600.0
    minimum_hypothesis_probability: float = 0.05

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_prefix", require_id("scope_prefix", self.scope_prefix))
        for name in (
            "belief_prior",
            "verified_observation_reliability",
            "failed_observation_reliability",
            "claim_prior",
            "minimum_hypothesis_probability",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("max_probe_count", "checkpoint_history", "decision_history"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AgentContractError(f"{name} must be positive integer")
        for name in (
            "learn_from_failed_runs",
            "learn_read_only_actions",
            "preserve_run_worlds",
        ):
            if not isinstance(getattr(self, name), bool):
                raise AgentContractError(f"{name} must be boolean")
        stale = float(self.stale_evidence_seconds)
        if stale <= 0:
            raise AgentContractError("stale_evidence_seconds must be positive")
        object.__setattr__(self, "stale_evidence_seconds", stale)


@dataclass(frozen=True, slots=True)
class RunCognitiveState:
    run_id: str
    scope: str
    world: BeliefGraph
    loop_detector: LoopDetector
    created_at: float
    checkpoint_count: int = 0
    last_checkpoint_fingerprint: str | None = None
    last_evidence_fingerprint: str | None = None
    last_plan_fingerprint: str | None = None
    last_action_fingerprint: str | None = None
    last_answer_fingerprint: str | None = None
    loop_signals: LoopSignals = field(default_factory=LoopSignals)
    successful_verifications: int = 0
    failed_verifications: int = 0
    consecutive_failures: int = 0
    last_mode: CognitiveMode | None = None
    mode_repetition: int = 0
    intervention_count: int = 0
    decisions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "scope", require_id("scope", self.scope))
        if not isinstance(self.world, BeliefGraph):
            raise AgentContractError("world must be BeliefGraph")
        if not isinstance(self.loop_detector, LoopDetector):
            raise AgentContractError("loop_detector must be LoopDetector")
        if self.last_mode is not None and not isinstance(self.last_mode, CognitiveMode):
            object.__setattr__(self, "last_mode", CognitiveMode(str(self.last_mode)))
        for name in (
            "checkpoint_count",
            "successful_verifications",
            "failed_verifications",
            "consecutive_failures",
            "mode_repetition",
            "intervention_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        object.__setattr__(self, "decisions", tuple(require_id("decision_id", item) for item in self.decisions))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CortexCheckpointAssessment:
    run_id: str
    checkpoint_sequence: int
    decision: MetaDecision
    probes: tuple[CounterfactualProbe, ...]
    world_fingerprint: str
    action_selection: SkillSelection | None
    loop_signals: LoopSignals
    recommended_skill_id: str | None
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CortexRunReport:
    run_id: str
    success: bool
    result_reason: str
    world_fingerprint: str
    belief_count: int
    hypothesis_count: int
    world_entropy_bits: float
    decisions: tuple[MetaDecision, ...]
    top_hypotheses: tuple[Hypothesis, ...]
    unresolved_probes: tuple[CounterfactualProbe, ...]
    learned_skill_ids: tuple[str, ...]
    skill_library_fingerprint: str
    anomalies: tuple[str, ...]
    report_fingerprint: str


class JeevesCortex:
    """Cross-run cognitive supervisor that cannot bypass runtime safety gates."""

    def __init__(
        self,
        *,
        world_model: WorldModel | None = None,
        skill_library: SkillLibrary | None = None,
        meta_controller: MetaController | None = None,
        config: CortexConfig | None = None,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or CortexConfig()
        self._clock = clock
        self._monotonic = monotonic
        self.world_model = world_model or WorldModel(clock=clock)
        self.skills = skill_library or SkillLibrary(clock=clock)
        self.meta = meta_controller or MetaController(
            policy=MetaPolicy(max_interventions=self.config.decision_history),
            clock=clock,
            history_limit=self.config.decision_history * 4,
        )
        self._runs: dict[str, RunCognitiveState] = {}
        self._checkpoint_cache: dict[str, deque[RunCheckpoint]] = {}
        self._checkpoint_assessments: dict[
            str, dict[str, CortexCheckpointAssessment]
        ] = {}
        self._result_reports: dict[str, CortexRunReport] = {}
        self._lock = threading.RLock()

    def begin(self, inputs: RunInputs, *, run_id: str | None = None, evidence_ledger: EvidenceLedger | None = None) -> RunCognitiveState:
        if not isinstance(inputs, RunInputs):
            raise TypeError("inputs must be RunInputs")
        resolved = run_id or inputs.run_id
        if resolved is None:
            resolved = stable_id(
                "cortex_run",
                {
                    "goal": inputs.goal.goal_id,
                    "tenant": inputs.tenant_id,
                    "user": inputs.user_id,
                    "workspace": inputs.workspace_id,
                    "session": inputs.session_id,
                    "at": self._clock(),
                },
            )
        resolved = require_id("run_id", resolved)
        scope = self._scope(inputs, resolved)
        with self._lock:
            prior = self._runs.get(resolved)
            if prior is not None:
                if prior.scope != scope:
                    raise CortexError("existing cortex run scope does not match inputs")
                if prior.metadata.get("goal_id") != inputs.goal.goal_id:
                    raise CortexError("existing cortex run goal does not match inputs")
                if evidence_ledger is not None:
                    try:
                        prior.world.bind_evidence_ledger(evidence_ledger)
                    except WorldModelError as exc:
                        raise CortexError(str(exc)) from exc
                return prior
            world = self.world_model.graph(scope, evidence_ledger=evidence_ledger)
            state = RunCognitiveState(
                run_id=resolved,
                scope=scope,
                world=world,
                loop_detector=LoopDetector(),
                created_at=self._clock(),
                metadata={
                    "goal_id": inputs.goal.goal_id,
                    "tenant_id": inputs.tenant_id,
                    "user_id": inputs.user_id,
                    "workspace_id": inputs.workspace_id,
                },
            )
            self._runs[resolved] = state
            self._checkpoint_cache[resolved] = deque(maxlen=self.config.checkpoint_history)
        self._seed_goal_world(state, inputs)
        return state

    def state(self, run_id: str) -> RunCognitiveState | None:
        with self._lock:
            return self._runs.get(require_id("run_id", run_id))

    def require_state(self, run_id: str) -> RunCognitiveState:
        state = self.state(run_id)
        if state is None:
            raise CortexError(f"unknown cortex run {run_id}")
        return state

    def observe_checkpoint(
        self,
        inputs: RunInputs,
        checkpoint: RunCheckpoint,
        *,
        proposed_skill_id: str | None = None,
        current_risk: RiskTier = RiskTier.READ_ONLY,
        confirmation_required: bool = False,
        blast_radius: float = 0.0,
        grounded_claim_fraction: float = 1.0,
    ) -> CortexCheckpointAssessment:
        if not isinstance(checkpoint, RunCheckpoint):
            raise TypeError("checkpoint must be RunCheckpoint")
        state = self.state(checkpoint.run_id) or self.begin(inputs, run_id=checkpoint.run_id)
        if checkpoint.goal_id != inputs.goal.goal_id:
            raise CortexError("checkpoint goal does not match cortex run goal")
        with self._lock:
            cached = self._checkpoint_assessments.get(
                checkpoint.run_id, {}
            ).get(checkpoint.fingerprint)
        if cached is not None:
            return cached
        self._cache_checkpoint(checkpoint)
        self._ingest_checkpoint_evidence(state, checkpoint)
        self._ingest_plan_structure(state, checkpoint.plan)
        self._ingest_observation_beliefs(state, checkpoint.observations)
        action_fingerprint = self._latest_action_fingerprint(checkpoint)
        evidence_fingerprint = stable_fingerprint(
            [(item.evidence_id, item.fingerprint) for item in checkpoint.evidence]
        )
        plan_fingerprint = stable_fingerprint(checkpoint.plan.to_dict()) if checkpoint.plan is not None else None
        loop = state.loop_detector.observe(
            state_fingerprint=checkpoint.fingerprint,
            action_fingerprint=action_fingerprint,
            evidence_fingerprint=evidence_fingerprint,
            plan_fingerprint=plan_fingerprint,
        )
        successful, failed, consecutive = self._verification_progress(checkpoint)
        last_mode = state.last_mode
        mode_repetition = state.mode_repetition
        elapsed = max(0.0, self._monotonic() - self._created_monotonic_estimate(state))
        context = self._context_from_inputs(inputs, checkpoint)
        meta_builder = MetaStateBuilder(
            run_id=state.run_id,
            phase=checkpoint.phase,
            usage=checkpoint.usage,
            budget_contract=inputs.budget,
            started_at=self._monotonic() - elapsed,
            plan=checkpoint.plan,
            world=state.world,
            skill_library=self.skills,
            skill_id=proposed_skill_id,
            context=context,
            risk=RiskSignals(
                current_risk=current_risk,
                confirmation_required=confirmation_required,
                irreversible=current_risk is RiskTier.HIGH_IMPACT,
                external_side_effect=current_risk in {RiskTier.EXTERNAL, RiskTier.HIGH_IMPACT},
                blast_radius=blast_radius,
            ),
            loop=loop,
            goal_complete=bool(checkpoint.plan and checkpoint.plan.complete),
            pending_verification=checkpoint.phase is AgentPhase.VERIFYING,
            pending_confirmation=confirmation_required,
            successful_verifications=successful,
            failed_verifications=failed,
            consecutive_failures=consecutive,
            replans=checkpoint.replan_count,
            evidence_count=len(checkpoint.evidence),
            stale_evidence_fraction=self._stale_fraction(checkpoint.evidence),
            grounded_claim_fraction=grounded_claim_fraction,
            last_mode=last_mode,
            mode_repetition=mode_repetition,
            intervention_count=state.intervention_count,
            metadata={"checkpoint_sequence": checkpoint.sequence},
        )
        meta_state = meta_builder.build(now_monotonic=self._monotonic())
        decision = self.meta.decide(meta_state)
        selection = self._skill_selection(checkpoint, context, current_risk)
        recommended_skill_id = selection.selected.skill_id if selection and selection.selected else None
        notes = list(self._assessment_notes(state, checkpoint, decision, selection))
        updated_state = replace(
            state,
            checkpoint_count=state.checkpoint_count + 1,
            last_checkpoint_fingerprint=checkpoint.fingerprint,
            last_evidence_fingerprint=evidence_fingerprint,
            last_plan_fingerprint=plan_fingerprint,
            last_action_fingerprint=action_fingerprint,
            loop_signals=loop,
            successful_verifications=successful,
            failed_verifications=failed,
            consecutive_failures=consecutive,
            last_mode=decision.mode,
            mode_repetition=(state.mode_repetition + 1 if state.last_mode == decision.mode else 1),
            intervention_count=state.intervention_count + 1,
            decisions=state.decisions + (decision.decision_id,),
        )
        with self._lock:
            self._runs[state.run_id] = updated_state
        probes = updated_state.world.ranked_probes(
            limit=self.config.max_probe_count,
            minimum_entropy_bits=0.05,
        )
        assessment = CortexCheckpointAssessment(
            run_id=state.run_id,
            checkpoint_sequence=checkpoint.sequence,
            decision=decision,
            probes=probes,
            world_fingerprint=updated_state.world.snapshot(persist=False).fingerprint,
            action_selection=selection,
            loop_signals=loop,
            recommended_skill_id=recommended_skill_id,
            notes=tuple(notes),
        )
        with self._lock:
            self._checkpoint_assessments.setdefault(
                state.run_id, {}
            )[checkpoint.fingerprint] = assessment
        return assessment

    def observe_result(
        self,
        inputs: RunInputs,
        result: AgentResult,
        *,
        verification_scores: Mapping[str, float] | None = None,
        action_costs: Mapping[str, float] | None = None,
        action_risks: Mapping[str, RiskTier | str] | None = None,
    ) -> CortexRunReport:
        if not isinstance(result, AgentResult):
            raise TypeError("result must be AgentResult")
        state = self.state(result.run_id) or self.begin(inputs, run_id=result.run_id)
        self._ingest_result_claims(state, result.claims)
        learned = self._learn_actions(
            state,
            result,
            verification_scores=verification_scores or {},
            action_costs=action_costs or {},
            action_risks=action_risks or {},
        )
        self._link_action_outcome_beliefs(state, result)
        visible_hypotheses = tuple(
            hypothesis
            for hypothesis in state.world.hypotheses(refresh=True)
            if hypothesis.posterior >= self.config.minimum_hypothesis_probability
        )
        top_hypotheses = visible_hypotheses[:5]
        unresolved = state.world.ranked_probes(
            limit=self.config.max_probe_count,
            minimum_entropy_bits=0.10,
        )
        anomalies = self._result_anomalies(state, result)
        decisions = self.meta.history(run_id=result.run_id)
        world_fingerprint = state.world.snapshot(persist=False).fingerprint
        payload = {
            "run": result.run_id,
            "success": result.success,
            "reason": result.reason.value,
            "world": world_fingerprint,
            "decisions": [item.decision_id for item in decisions],
            "skills": learned,
            "anomalies": anomalies,
            "result_trace": result.trace_fingerprint,
        }
        report = CortexRunReport(
            run_id=result.run_id,
            success=result.success,
            result_reason=result.reason.value,
            world_fingerprint=world_fingerprint,
            belief_count=len(state.world.beliefs()),
            hypothesis_count=len(visible_hypotheses),
            world_entropy_bits=state.world.world_entropy_bits(),
            decisions=decisions,
            top_hypotheses=top_hypotheses,
            unresolved_probes=unresolved,
            learned_skill_ids=tuple(sorted(learned)),
            skill_library_fingerprint=self.skills.fingerprint,
            anomalies=tuple(anomalies),
            report_fingerprint=stable_fingerprint(payload),
        )
        with self._lock:
            self._result_reports[result.run_id] = report
            if not self.config.preserve_run_worlds:
                self._runs.pop(result.run_id, None)
                self._checkpoint_cache.pop(result.run_id, None)
                self._checkpoint_assessments.pop(result.run_id, None)
        if not self.config.preserve_run_worlds:
            self.world_model.discard(state.scope)
        return report

    def report(self, run_id: str) -> CortexRunReport | None:
        with self._lock:
            return self._result_reports.get(require_id("run_id", run_id))

    def information_questions(self, run_id: str, *, limit: int | None = None) -> tuple[dict[str, Any], ...]:
        state = self.require_state(run_id)
        probes = state.world.ranked_probes(limit=limit or self.config.max_probe_count, minimum_entropy_bits=0.05)
        questions: list[dict[str, Any]] = []
        for probe in probes:
            belief = state.world.require_belief(probe.proposition_id)
            proposition = belief.proposition
            questions.append(
                {
                    "probe_id": probe.probe_id,
                    "proposition_id": probe.proposition_id,
                    "question": self._question_for(proposition),
                    "current_probability": probe.current_probability,
                    "expected_information_gain_bits": probe.expected_information_gain_bits,
                    "priority": probe.priority,
                    "rationale": probe.rationale,
                }
            )
        return tuple(questions)

    def choose_skill(
        self,
        *,
        capabilities: Sequence[str],
        context: ContextSignature | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
        top_k: int = 5,
    ) -> SkillSelection:
        return self.skills.select(
            required_capabilities=capabilities,
            context=context or ContextSignature(),
            maximum_risk=maximum_risk,
            top_k=top_k,
        )

    def register_skill(self, spec: SkillSpec) -> None:
        self.skills.register(spec)

    def rollback_world(self, run_id: str, snapshot_id: str) -> str:
        state = self.require_state(run_id)
        snapshot = state.world.rollback(snapshot_id)
        return snapshot.snapshot_id

    def snapshot_world(self, run_id: str) -> str:
        state = self.require_state(run_id)
        return state.world.snapshot(persist=True).snapshot_id

    def global_summary(self) -> dict[str, Any]:
        with self._lock:
            run_ids = sorted(self._runs)
            reports = sorted(self._result_reports)
        return {
            "active_or_retained_runs": run_ids,
            "report_runs": reports,
            "worlds": self.world_model.summary(),
            "skills": self.skills.summary(),
            "meta": self.meta.stats(),
            "fingerprint": stable_fingerprint(
                {
                    "world": self.world_model.fingerprint,
                    "skills": self.skills.fingerprint,
                    "meta": self.meta.stats().get("fingerprint"),
                    "runs": run_ids,
                    "reports": reports,
                }
            ),
        }

    def _scope(self, inputs: RunInputs, run_id: str) -> str:
        return require_id(
            "scope",
            f"{self.config.scope_prefix}:{stable_fingerprint((inputs.tenant_id, inputs.user_id, inputs.workspace_id, run_id))[:24]}",
        )

    def _seed_goal_world(self, state: RunCognitiveState, inputs: RunInputs) -> None:
        goal_prop = Proposition.create(
            subject=f"goal:{inputs.goal.goal_id}",
            predicate="objective",
            object=inputs.goal.objective,
            scope=state.scope,
            metadata={"success_criteria": inputs.goal.success_criteria, "constraints": inputs.goal.constraints},
        )
        state.world.upsert_proposition(goal_prop, prior=0.99, locked=True)
        for index, criterion in enumerate(inputs.goal.success_criteria, start=1):
            criterion_prop = Proposition.create(
                subject=f"goal:{inputs.goal.goal_id}",
                predicate="success_criterion",
                object=criterion,
                scope=state.scope,
                metadata={"criterion_index": index},
            )
            state.world.upsert_proposition(criterion_prop, prior=self.config.belief_prior)
            state.world.add_edge(goal_prop.proposition_id, criterion_prop.proposition_id, EdgeKind.ENABLES, weight=1.0, confidence=1.0)

    def _cache_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        with self._lock:
            history = self._checkpoint_cache.setdefault(checkpoint.run_id, deque(maxlen=self.config.checkpoint_history))
            if history and checkpoint.sequence <= history[-1].sequence:
                if checkpoint.fingerprint == history[-1].fingerprint:
                    return
                raise CortexError("checkpoint sequence regressed or forked")
            history.append(checkpoint)

    def _ingest_checkpoint_evidence(self, state: RunCognitiveState, checkpoint: RunCheckpoint) -> None:
        for artifact in checkpoint.evidence:
            proposition = Proposition.create(
                subject=f"evidence:{artifact.evidence_id}",
                predicate="observed",
                object=artifact.payload,
                scope=state.scope,
                temporal_key=str(artifact.observed_at),
                metadata={"source": artifact.source, "kind": artifact.kind.value},
            )
            belief = state.world.upsert_proposition(proposition, prior=self.config.belief_prior)
            reliability = min(self.config.verified_observation_reliability, artifact.confidence)
            if artifact.evidence_id not in belief.supporting_evidence_ids:
                try:
                    state.world.revise(
                        BeliefUpdate(
                            proposition_id=proposition.proposition_id,
                            evidence_id=artifact.evidence_id if state.world.evidence_ledger is not None else None,
                            direction=1,
                            reliability=reliability,
                            reason="checkpoint verified evidence",
                            metadata={"checkpoint": checkpoint.sequence},
                        )
                    )
                except Exception:
                    # A detached cortex may not share the runtime ledger.  In
                    # that case preserve the proposition without inventing an
                    # evidence binding.
                    if state.world.evidence_ledger is not None:
                        raise

    def _ingest_plan_structure(self, state: RunCognitiveState, plan: Plan | None) -> None:
        if plan is None:
            return
        step_props: dict[str, Proposition] = {}
        for step in plan.steps:
            proposition = Proposition.create(
                subject=f"plan:{plan.plan_id}",
                predicate="step",
                object={
                    "step_id": step.step_id,
                    "title": step.title,
                    "tool": step.tool,
                    "risk": step.risk.value,
                    "status": step.status.value,
                    "verification": step.verification,
                },
                scope=state.scope,
                metadata={"plan_version": plan.version},
            )
            prior = 0.90 if step.status in {step.status.SUCCEEDED, step.status.SKIPPED} else 0.55
            state.world.upsert_proposition(proposition, prior=prior)
            step_props[step.step_id] = proposition
        for step in plan.steps:
            target = step_props[step.step_id]
            for dependency in step.dependencies:
                source = step_props.get(dependency)
                if source is not None:
                    state.world.add_edge(source.proposition_id, target.proposition_id, EdgeKind.ENABLES, weight=1.0, confidence=1.0)

    def _ingest_observation_beliefs(self, state: RunCognitiveState, observations: Sequence[ToolObservation]) -> None:
        for observation in observations:
            proposition = Proposition.create(
                subject=f"tool:{observation.tool_name}",
                predicate="call_succeeded",
                object={"call_id": observation.call_id},
                polarity=observation.ok,
                scope=state.scope,
                metadata={"latency_ms": observation.latency_ms, "cached": observation.cached},
            )
            prior = 0.5
            belief = state.world.upsert_proposition(proposition, prior=prior)
            if len(belief.revision_ids) > 1:
                continue
            reliability = self.config.verified_observation_reliability if observation.ok else self.config.failed_observation_reliability
            state.world.revise(
                BeliefUpdate(
                    proposition_id=proposition.proposition_id,
                    evidence_id=None,
                    direction=1,
                    reliability=reliability,
                    reason="observed tool execution outcome",
                    metadata={"call_id": observation.call_id},
                )
            )

    def _ingest_result_claims(self, state: RunCognitiveState, claims: Sequence[Claim]) -> None:
        for claim in claims:
            try:
                state.world.from_claim(claim, scope=state.scope, prior_strength=self.config.claim_prior)
            except Exception:
                # Claim evidence references may be valid in the runtime ledger
                # while the cortex is detached.  Preserve the hypothesis with
                # a conservative prior rather than silently trusting it.
                proposition = Proposition.create(
                    claim.subject or "claim",
                    "asserts",
                    claim.text,
                    scope=state.scope,
                    metadata={"claim_id": claim.claim_id, "detached_evidence": True},
                )
                state.world.upsert_proposition(proposition, prior=min(self.config.claim_prior, claim.confidence))

    def _learn_actions(
        self,
        state: RunCognitiveState,
        result: AgentResult,
        *,
        verification_scores: Mapping[str, float],
        action_costs: Mapping[str, float],
        action_risks: Mapping[str, RiskTier | str],
    ) -> set[str]:
        learned: set[str] = set()
        if not result.success and not self.config.learn_from_failed_runs:
            return learned
        context = ContextSignature(
            domain="jeeves",
            environment="runtime",
            tags=(result.reason.value, "success" if result.success else "failure"),
            feature_buckets={"goal": result.goal_id[:32]},
        )
        for observation in result.observations:
            score = probability(
                "verification_score",
                verification_scores.get(
                    observation.call_id,
                    1.0 if observation.ok and result.success else 0.5,
                ),
            )
            verified = score >= 0.6 and observation.ok
            raw_risk = action_risks.get(observation.call_id, RiskTier.READ_ONLY)
            risk = raw_risk if isinstance(raw_risk, RiskTier) else RiskTier(str(raw_risk))
            if risk is RiskTier.READ_ONLY and not self.config.learn_read_only_actions:
                continue
            profile = self.skills.record_tool_observation(
                run_id=result.run_id,
                tool_name=observation.tool_name,
                observation=observation,
                context=context,
                verified=verified,
                verification_score=score,
                cost=max(0.0, float(action_costs.get(observation.call_id, 0.0))),
                failure_mode=observation.error,
                risk=risk,
            )
            learned.add(profile.spec.skill_id)
        return learned

    def _link_action_outcome_beliefs(self, state: RunCognitiveState, result: AgentResult) -> None:
        outcome_prop = Proposition.create(
            subject=f"run:{result.run_id}",
            predicate="goal_reached",
            object=result.success,
            polarity=result.success,
            scope=state.scope,
            metadata={"termination_reason": result.reason.value},
        )
        state.world.upsert_proposition(outcome_prop, prior=0.95 if result.success else 0.80)
        for observation in result.observations:
            action_candidates = [
                belief
                for belief in state.world.beliefs()
                if belief.proposition.subject == f"tool:{observation.tool_name}"
                and isinstance(belief.proposition.object, dict)
                and belief.proposition.object.get("call_id") == observation.call_id
            ]
            for action_belief in action_candidates:
                state.world.add_edge(
                    action_belief.proposition_id,
                    outcome_prop.proposition_id,
                    EdgeKind.CAUSES if result.success and observation.ok else EdgeKind.CORRELATES,
                    weight=0.7 if observation.ok else -0.4,
                    confidence=0.65,
                    metadata={"run_id": result.run_id},
                )

    def _verification_progress(self, checkpoint: RunCheckpoint) -> tuple[int, int, int]:
        successful = 0
        failed = 0
        consecutive = 0
        if checkpoint.plan is not None:
            for step in checkpoint.plan.steps:
                if step.status is step.status.SUCCEEDED:
                    successful += 1
                    consecutive = 0
                elif step.status in {step.status.FAILED, step.status.BLOCKED}:
                    failed += 1
                    consecutive += 1
        return successful, failed, consecutive

    def _skill_selection(self, checkpoint: RunCheckpoint, context: ContextSignature, maximum_risk: RiskTier) -> SkillSelection | None:
        if checkpoint.plan is None:
            return None
        ready = checkpoint.plan.ready_steps()
        if not ready:
            return None
        step = ready[0]
        if step.tool is None:
            return None
        skill = SkillSpec.tool(step.tool, risk=step.risk, capabilities=(f"tool:{step.tool}",))
        if self.skills.profile(skill.skill_id) is None:
            self.skills.register(skill)
        return self.skills.select(
            required_capabilities=(f"tool:{step.tool}",),
            context=context,
            maximum_risk=maximum_risk,
            top_k=5,
        )

    def _assessment_notes(
        self,
        state: RunCognitiveState,
        checkpoint: RunCheckpoint,
        decision: MetaDecision,
        selection: SkillSelection | None,
    ) -> tuple[str, ...]:
        notes: list[str] = []
        if state.loop_signals.severity >= 0.5:
            notes.append(f"loop severity elevated: {state.loop_signals.severity:.3f}")
        if decision.mode is CognitiveMode.RESOLVE_CONTRADICTION:
            notes.append("contradictory beliefs should be discriminated before finalization")
        if decision.mode is CognitiveMode.SEEK_INFORMATION:
            probes = state.world.ranked_probes(limit=1, minimum_entropy_bits=0.0)
            if probes:
                notes.append(f"highest information-gain probe: {probes[0].probe_id}")
        if selection and selection.selected:
            notes.append(f"empirical skill recommendation: {selection.selected.skill_id} score={selection.selected.total:.3f}")
        if checkpoint.replan_count:
            notes.append(f"plan has been revised {checkpoint.replan_count} time(s)")
        return tuple(notes)

    def _result_anomalies(self, state: RunCognitiveState, result: AgentResult) -> list[str]:
        anomalies: list[str] = []
        if result.success and not result.claims and result.answer.strip():
            anomalies.append("successful answer contains no structured grounded claims")
        if result.success and state.world.world_entropy_bits() > max(4.0, len(state.world.beliefs()) * 0.6):
            anomalies.append("run succeeded while retained world model remains highly uncertain")
        if state.loop_signals.severity >= 0.8:
            anomalies.append("high loop/stagnation severity observed")
        if any(not observation.ok for observation in result.observations) and result.success:
            anomalies.append("run succeeded despite one or more failed tool observations")
        if result.plan is not None and not result.plan.complete and result.success:
            anomalies.append("result marked successful while plan is incomplete")
        return anomalies

    def _context_from_inputs(self, inputs: RunInputs, checkpoint: RunCheckpoint) -> ContextSignature:
        tags = [checkpoint.phase.value]
        if checkpoint.plan is not None:
            tags.extend(sorted({step.risk.value for step in checkpoint.plan.steps}))
        return ContextSignature(
            domain="jeeves",
            environment=inputs.workspace_id,
            tags=tuple(tags[:16]),
            feature_buckets={
                "tenant": inputs.tenant_id,
                "goal": inputs.goal.goal_id,
                "plan_version": str(checkpoint.plan.version if checkpoint.plan else 0),
            },
        )

    def _stale_fraction(self, evidence: Sequence[EvidenceArtifact]) -> float:
        if not evidence:
            return 0.0
        now = self._clock()
        stale = sum(1 for item in evidence if now - item.observed_at > self.config.stale_evidence_seconds)
        return stale / len(evidence)

    def _latest_action_fingerprint(self, checkpoint: RunCheckpoint) -> str | None:
        if checkpoint.observations:
            item = checkpoint.observations[-1]
            return stable_fingerprint((item.tool_name, item.call_id, item.ok, item.payload, item.error))
        if checkpoint.plan is not None:
            running = [step for step in checkpoint.plan.steps if step.status is step.status.RUNNING]
            if running:
                step = running[-1]
                return stable_fingerprint((step.step_id, step.tool, step.arguments, step.attempts))
        return None

    def _created_monotonic_estimate(self, state: RunCognitiveState) -> float:
        # Wall and monotonic clocks are not interchangeable.  We only need a
        # stable elapsed estimate for meta-budget pressure; retained runs start
        # a fresh monotonic segment when first observed by this process.
        elapsed_wall = max(0.0, self._clock() - state.created_at)
        return max(0.0, self._monotonic() - elapsed_wall)

    @staticmethod
    def _question_for(proposition: Proposition) -> str:
        polarity = "is true" if proposition.polarity else "is false"
        return (
            f"What independent observation would best determine whether "
            f"{proposition.subject} {proposition.predicate} {proposition.object!r} {polarity}?"
        )
