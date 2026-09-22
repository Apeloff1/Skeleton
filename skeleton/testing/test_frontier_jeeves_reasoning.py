from __future__ import annotations

from types import SimpleNamespace

from skeleton.jeeves.agent.adaptive_runtime import AdaptiveConfig, AdaptiveJeevesRuntime
from skeleton.jeeves.agent.adversarial_verification import CouncilVerdict, Verdict
from skeleton.jeeves.agent.deliberation import (
    CandidateProposal,
    CandidateScore,
    DeliberationMode,
    SearchResult,
    SpecialistRole,
)
from skeleton.jeeves.agent.frontier_adjudication import HostCandidateAdjudicator
from skeleton.jeeves.agent.frontier_consensus import ConsensusSelector
from skeleton.jeeves.agent.evaluation import EvalResult
from skeleton.jeeves.agent.evidence import EvidenceArtifact, EvidenceLedger
from skeleton.jeeves.agent.frontier_feedback import (
    FrontierEvalFeedback,
    FrontierFeedbackRecommendation,
    FrontierReasoningFeedback,
)
from skeleton.jeeves.agent.frontier_policy_tuning import FrontierPolicyTuner
from skeleton.jeeves.agent.frontier_trials import FrontierTrialEvaluator
from skeleton.jeeves.agent.frontier_reasoning import (
    EscalationCause,
    FrontierReasoningCoordinator,
    FrontierReasoningPolicy,
    InferenceDisposition,
)
from skeleton.jeeves.agent.lens_fusion import LensSignal
from skeleton.jeeves.agent.rational_metareasoning import (
    ComputationAction,
    ComputationOutcome,
    DecisionAlternative,
    MetaActionKind,
    MetaBudget,
    MetaState,
)
from skeleton.jeeves.agent.semantic_lenses import LensFamily
from skeleton.jeeves.agent.types import (
    EvidenceKind,
    EvidenceRef,
    RiskTier,
    stable_fingerprint,
)


def _evidence(name: str, confidence: float = 0.9) -> EvidenceRef:
    token = stable_fingerprint({"evidence": name})
    return EvidenceRef(
        evidence_id=f"evidence:{name}",
        kind=EvidenceKind.FIXTURE,
        source="frontier-reasoning-test",
        fingerprint=token,
        confidence=confidence,
        observed_at=1.0,
    )


def _candidate(
    name: str,
    *,
    confidence: float,
    action: str,
    outcome: str,
    evidence: tuple[EvidenceRef, ...] = (),
) -> CandidateProposal:
    return CandidateProposal(
        candidate_id=f"candidate:{name}",
        parent_id=None,
        depth=0,
        role=SpecialistRole.SOLVER,
        summary=f"Candidate {name}",
        proposed_action=action,
        predicted_outcome=outcome,
        confidence=confidence,
        evidence=evidence,
    )


def _score(
    candidate: CandidateProposal,
    *,
    total: float,
    evidence_quality: float,
    verifier: float,
    risk_penalty: float = 0.05,
    cost_penalty: float = 0.0,
) -> CandidateScore:
    return CandidateScore(
        candidate_id=candidate.candidate_id,
        utility=max(-1.0, min(1.0, total)),
        evidence_quality=evidence_quality,
        confidence_quality=candidate.confidence,
        risk_penalty=risk_penalty,
        cost_penalty=cost_penalty,
        novelty_bonus=0.5,
        verifier_score=verifier,
        total=total,
        reasons=(),
    )


def _search(
    *pairs: tuple[CandidateProposal, CandidateScore],
    trace: str = "search-trace",
) -> SearchResult:
    return SearchResult(
        mode=DeliberationMode.COMMITTEE,
        best=pairs[0][0] if pairs else None,
        ranking=tuple(pairs),
        explored=tuple(candidate for candidate, _ in pairs),
        ledger={"model_calls": 2, "candidates": len(pairs)},
        stopped_reason="fixture complete",
        trace_fingerprint=stable_fingerprint(trace),
    )


def _council(verdict: Verdict, *, lower: float = 0.8) -> CouncilVerdict:
    return CouncilVerdict(
        subject_id="subject:frontier",
        verdict=verdict,
        score=0.9 if verdict is Verdict.ACCEPT else 0.2,
        lower_bound=lower,
        upper_bound=0.96,
        host_score=0.92,
        weighted_votes=(),
        axis_scores={},
        challenges=(),
        quorum_satisfied=True,
        reward_hacking_alarm=False,
        reasons=(),
        fingerprint=stable_fingerprint(
            {"verdict": verdict.value, "lower": lower}
        ),
    )


def _strong_search(*, trace: str = "search-trace") -> SearchResult:
    first = _candidate(
        "primary",
        confidence=0.95,
        action="apply verified patch",
        outcome="tests pass and behavior remains compatible",
        evidence=(_evidence("primary"),),
    )
    second = _candidate(
        "fallback",
        confidence=0.40,
        action="defer patch",
        outcome="behavior remains unchanged",
        evidence=(_evidence("fallback", 0.4),),
    )
    return _search(
        (
            first,
            _score(
                first,
                total=0.95,
                evidence_quality=0.90,
                verifier=0.95,
            ),
        ),
        (
            second,
            _score(
                second,
                total=0.10,
                evidence_quality=0.30,
                verifier=0.30,
                risk_penalty=0.20,
            ),
        ),
        trace=trace,
    )


def test_clear_low_risk_candidate_commits() -> None:
    coordinator = FrontierReasoningCoordinator()

    decision = coordinator.decide(_strong_search())

    assert decision.disposition is InferenceDisposition.COMMIT
    assert decision.committed_candidate is not None
    assert decision.committed_candidate.candidate_id == "candidate:primary"
    assert decision.assessments[0].absolute_quality > 0.8
    assert decision.assessments[0].choice_probability > 0.8
    assert EscalationCause.LOW_MARGIN not in decision.causes


def test_close_competing_actions_trigger_more_deliberation() -> None:
    left = _candidate(
        "left",
        confidence=0.92,
        action="use strategy alpha",
        outcome="alpha succeeds",
        evidence=(_evidence("shared"),),
    )
    right = _candidate(
        "right",
        confidence=0.90,
        action="use strategy beta",
        outcome="beta succeeds",
        evidence=(_evidence("shared"),),
    )
    search = _search(
        (
            left,
            _score(
                left,
                total=0.90,
                evidence_quality=0.90,
                verifier=0.90,
            ),
        ),
        (
            right,
            _score(
                right,
                total=0.88,
                evidence_quality=0.89,
                verifier=0.89,
            ),
        ),
    )

    decision = FrontierReasoningCoordinator().decide(search)

    assert decision.disposition is InferenceDisposition.DELIBERATE
    assert decision.diagnostics.normalized_entropy > 0.95
    assert decision.diagnostics.action_disagreement > 0.45
    assert EscalationCause.LOW_MARGIN in decision.causes
    assert EscalationCause.ACTION_DISAGREEMENT in decision.causes


def test_mutating_candidate_requires_explicit_verification() -> None:
    decision = FrontierReasoningCoordinator().decide(
        _strong_search(),
        risk=RiskTier.MUTATING,
    )

    assert decision.disposition is InferenceDisposition.VERIFY
    assert EscalationCause.VERIFICATION_REQUIRED in decision.causes
    assert decision.committed_candidate is None


def test_mutating_candidate_can_commit_after_strong_council_acceptance() -> None:
    decision = FrontierReasoningCoordinator().decide(
        _strong_search(),
        risk=RiskTier.MUTATING,
        verification=_council(Verdict.ACCEPT, lower=0.82),
    )

    assert decision.disposition is InferenceDisposition.COMMIT
    assert decision.committed_candidate is not None
    assert EscalationCause.VERIFICATION_REQUIRED not in decision.causes


def test_verifier_rejection_blocks_high_confidence_candidate() -> None:
    decision = FrontierReasoningCoordinator().decide(
        _strong_search(),
        verification=_council(Verdict.REJECT, lower=0.10),
    )

    assert decision.disposition is InferenceDisposition.ABSTAIN
    assert EscalationCause.VERIFICATION_REJECTED in decision.causes
    assert decision.committed_candidate is None


def test_semantic_lens_conflict_forces_deliberation() -> None:
    primary = _strong_search()
    signals = (
        LensSignal(
            signal_id="lens:positive",
            lens_key="system-positive",
            family=LensFamily.SYSTEM,
            probability=0.90,
            confidence=1.0,
            ambiguity=0.0,
            reliability=1.0,
            epistemic_strength=1.0,
            calibration_group="system-a",
        ),
        LensSignal(
            signal_id="lens:negative",
            lens_key="cognitive-negative",
            family=LensFamily.COGNITIVE,
            probability=0.10,
            confidence=1.0,
            ambiguity=0.0,
            reliability=1.0,
            epistemic_strength=1.0,
            calibration_group="cognitive-b",
        ),
    )

    decision = FrontierReasoningCoordinator().decide(
        primary,
        lens_signals=signals,
    )

    assert decision.lens_fusion is not None
    assert decision.lens_fusion.conflict_strength >= 0.99
    assert decision.lens_fusion.abstain is True
    assert EscalationCause.LENS_CONFLICT in decision.causes
    assert decision.disposition is InferenceDisposition.DELIBERATE


def test_positive_value_of_computation_postpones_commit() -> None:
    state = MetaState(
        decisions=(
            DecisionAlternative("patch", expected_utility=0.60),
            DecisionAlternative("defer", expected_utility=0.50),
        ),
        belief_entropy=0.80,
        current_risk=0.25,
        budget=MetaBudget(
            remaining_compute=10.0,
            remaining_tokens=10_000,
            remaining_money=10.0,
            remaining_seconds=30.0,
        ),
    )
    action = ComputationAction(
        action_id="compute:counterfactual",
        kind=MetaActionKind.SIMULATE,
        outcomes=(
            ComputationOutcome(
                probability=0.5,
                posterior_utilities={"patch": 0.95, "defer": 0.30},
                posterior_entropy=0.30,
                posterior_risk=0.15,
                observation_label="patch robust",
            ),
            ComputationOutcome(
                probability=0.5,
                posterior_utilities={"patch": 0.30, "defer": 0.95},
                posterior_entropy=0.30,
                posterior_risk=0.15,
                observation_label="defer robust",
            ),
        ),
        compute_cost=0.02,
        delay_seconds=0.01,
        token_cost=100,
        evidence_producing=False,
    )

    decision = FrontierReasoningCoordinator().decide(
        _strong_search(),
        meta_state=state,
        computation_actions=(action,),
    )

    assert decision.metareasoning is not None
    assert decision.metareasoning.selected_action_id == "compute:counterfactual"
    assert decision.disposition is InferenceDisposition.DELIBERATE
    assert decision.next_computation_action_id == "compute:counterfactual"
    assert EscalationCause.POSITIVE_VALUE_OF_COMPUTATION in decision.causes


def test_evidence_producing_meta_action_routes_to_seek_evidence() -> None:
    state = MetaState(
        decisions=(
            DecisionAlternative("patch", expected_utility=0.55),
            DecisionAlternative("defer", expected_utility=0.50),
        ),
        belief_entropy=0.90,
        current_risk=0.30,
        budget=MetaBudget(
            remaining_compute=5.0,
            remaining_tokens=5_000,
            remaining_money=5.0,
            remaining_seconds=20.0,
        ),
        information_utility_rate=0.5,
    )
    action = ComputationAction(
        action_id="search:missing-evidence",
        kind=MetaActionKind.SEARCH,
        outcomes=(
            ComputationOutcome(
                probability=0.5,
                posterior_utilities={"patch": 0.90, "defer": 0.40},
                posterior_entropy=0.20,
                posterior_risk=0.15,
            ),
            ComputationOutcome(
                probability=0.5,
                posterior_utilities={"patch": 0.35, "defer": 0.85},
                posterior_entropy=0.20,
                posterior_risk=0.15,
            ),
        ),
        compute_cost=0.01,
        token_cost=50,
        evidence_producing=True,
        evidence_class="retrieval",
    )

    decision = FrontierReasoningCoordinator().decide(
        _strong_search(),
        meta_state=state,
        computation_actions=(action,),
    )

    assert decision.disposition is InferenceDisposition.SEEK_EVIDENCE
    assert decision.next_computation_action_id == "search:missing-evidence"


def test_low_evidence_quality_routes_to_seek_evidence() -> None:
    candidate = _candidate(
        "ungrounded",
        confidence=0.96,
        action="answer now",
        outcome="answer is accepted",
    )
    search = _search(
        (
            candidate,
            _score(
                candidate,
                total=0.95,
                evidence_quality=0.10,
                verifier=0.95,
            ),
        ),
    )

    decision = FrontierReasoningCoordinator().decide(search)

    assert decision.assessments[0].absolute_quality > 0.62
    assert EscalationCause.INSUFFICIENT_EVIDENCE in decision.causes
    assert decision.disposition is InferenceDisposition.SEEK_EVIDENCE


def test_strong_semantic_signal_cannot_rescue_low_quality_candidate() -> None:
    candidate = _candidate(
        "weak",
        confidence=0.35,
        action="guess",
        outcome="guess happens to work",
    )
    search = _search(
        (
            candidate,
            _score(
                candidate,
                total=-0.05,
                evidence_quality=0.25,
                verifier=0.35,
                risk_penalty=0.10,
            ),
        ),
    )
    signals = (
        LensSignal(
            signal_id="lens:optimistic",
            lens_key="optimistic-reading",
            family=LensFamily.NARRATIVE,
            probability=0.99,
            confidence=1.0,
            ambiguity=0.0,
            reliability=1.0,
            epistemic_strength=1.0,
            calibration_group="optimistic",
        ),
    )

    decision = FrontierReasoningCoordinator().decide(
        search,
        lens_signals=signals,
    )

    assert EscalationCause.LOW_ABSOLUTE_QUALITY in decision.causes
    assert decision.disposition is not InferenceDisposition.COMMIT
    assert decision.committed_candidate is None


def test_identical_inputs_produce_identical_replay_fingerprint() -> None:
    coordinator = FrontierReasoningCoordinator()
    search = _strong_search()

    first = coordinator.decide(search)
    second = coordinator.decide(search)

    assert first.fingerprint == second.fingerprint
    assert first.diagnostics.fingerprint == second.diagnostics.fingerprint
    assert tuple(item.fingerprint for item in first.assessments) == tuple(
        item.fingerprint for item in second.assessments
    )


def test_empty_search_abstains() -> None:
    decision = FrontierReasoningCoordinator().decide(_search())

    assert decision.disposition is InferenceDisposition.ABSTAIN
    assert decision.leading_candidate is None
    assert EscalationCause.NO_CANDIDATE in decision.causes



def test_best_of_n_consensus_can_override_single_high_score_outlier() -> None:
    outlier = _candidate(
        "outlier",
        confidence=0.97,
        action="rewrite the subsystem immediately",
        outcome="the subsystem is replaced",
        evidence=(_evidence("outlier"),),
    )
    agree_a = _candidate(
        "agree-a",
        confidence=0.86,
        action="preserve the subsystem and add a guarded adapter",
        outcome="compatibility is preserved while the adapter is introduced",
        evidence=(_evidence("agree-a"),),
    )
    agree_b = _candidate(
        "agree-b",
        confidence=0.84,
        action="preserve the subsystem and add a guarded adapter",
        outcome="compatibility is preserved while the adapter is introduced",
        evidence=(_evidence("agree-b"),),
    )
    search = _search(
        (outlier, _score(outlier, total=0.96, evidence_quality=0.92, verifier=0.92)),
        (agree_a, _score(agree_a, total=0.78, evidence_quality=0.86, verifier=0.88)),
        (agree_b, _score(agree_b, total=0.76, evidence_quality=0.84, verifier=0.86)),
    )

    consensus = ConsensusSelector().select(search)
    decision = FrontierReasoningCoordinator().decide(search)

    assert consensus.selected_candidate_id in {"candidate:agree-a", "candidate:agree-b"}
    assert decision.leading_candidate is not None
    assert decision.leading_candidate.candidate_id in {"candidate:agree-a", "candidate:agree-b"}
    assert decision.consensus is not None
    assert decision.consensus.agreement > 0.5
    assert decision.consensus.requires_more_sampling is False
    assert decision.disposition is InferenceDisposition.COMMIT


def test_feedback_tracks_verified_direct_and_escalated_outcomes() -> None:
    coordinator = FrontierReasoningCoordinator()
    feedback = FrontierReasoningFeedback()
    direct = coordinator.decide(_strong_search())
    escalated = coordinator.decide(_strong_search(trace="escalated-search"))

    feedback.observe(
        direct,
        verified_success=False,
        escalation_rounds=0,
        model_calls=2,
        estimated_tokens=1000,
    )
    feedback.observe(
        escalated,
        verified_success=True,
        escalation_rounds=1,
        model_calls=5,
        estimated_tokens=3000,
    )
    report = feedback.report()

    assert report.count == 2
    assert report.direct_success_rate == 0.0
    assert report.escalated_success_rate == 1.0
    assert report.observed_escalation_delta == 1.0
    assert report.mean_model_calls == 3.5
    efficiency = feedback.compute_efficiency()
    assert efficiency.incremental_model_calls == 3.0
    assert efficiency.incremental_estimated_tokens == 2000.0
    assert efficiency.success_gain_per_extra_model_call == 1.0 / 3.0
    assert efficiency.success_gain_per_1k_extra_tokens == 0.5
    assert report.fingerprint


def test_consensus_is_deterministic_for_identical_search() -> None:
    selector = ConsensusSelector()
    search = _strong_search()

    first = selector.select(search)
    second = selector.select(search)

    assert first.fingerprint == second.fingerprint
    assert first.selected_candidate_id == second.selected_candidate_id
    assert first.clusters == second.clusters



def test_matched_eval_feedback_blocks_pass_to_fail_regression() -> None:
    feedback = FrontierEvalFeedback()
    baseline = EvalResult(
        case_id="case:frontier-eval",
        run_id="run:baseline",
        score=0.80,
        passed=True,
        checks=(),
        result_fingerprint=stable_fingerprint("baseline"),
    )
    frontier = EvalResult(
        case_id="case:frontier-eval",
        run_id="run:frontier",
        score=0.72,
        passed=False,
        checks=(),
        result_fingerprint=stable_fingerprint("frontier"),
    )

    comparison = feedback.observe(baseline, frontier)
    report = feedback.report()
    gate = feedback.promotion_gate(
        minimum_cases=1,
        minimum_mean_delta=0.0,
        maximum_loss_rate=1.0,
        allow_pass_losses=0,
    )

    assert comparison.score_delta < 0.0
    assert report.pass_losses == 1
    assert report.regressed == 1
    assert gate.passed is False
    assert any("pass-to-fail" in reason for reason in gate.reasons)


def test_matched_eval_feedback_allows_measured_improvement() -> None:
    feedback = FrontierEvalFeedback()
    for index, (baseline_score, frontier_score) in enumerate(
        ((0.50, 0.70), (0.60, 0.75), (0.72, 0.80)),
        start=1,
    ):
        feedback.observe(
            EvalResult(
                case_id=f"case:gain-{index}",
                run_id=f"run:baseline-{index}",
                score=baseline_score,
                passed=baseline_score >= 0.70,
                checks=(),
                result_fingerprint=stable_fingerprint({"baseline": index}),
            ),
            EvalResult(
                case_id=f"case:gain-{index}",
                run_id=f"run:frontier-{index}",
                score=frontier_score,
                passed=frontier_score >= 0.70,
                checks=(),
                result_fingerprint=stable_fingerprint({"frontier": index}),
            ),
        )

    report = feedback.report()
    gate = feedback.promotion_gate(
        minimum_cases=3,
        minimum_mean_delta=0.05,
        maximum_loss_rate=0.10,
        allow_pass_losses=0,
    )

    assert report.improved == 3
    assert report.pass_gains >= 1
    assert report.mean_score_delta > 0.05
    assert gate.passed is True



def test_adaptive_specialist_generation_uses_virtual_model_call_dispatch() -> None:
    runtime = object.__new__(AdaptiveJeevesRuntime)
    runtime.adaptive_config = AdaptiveConfig(maximum_specialist_width=2)
    calls: list[dict[str, object]] = []

    def fake_model_call(state, **kwargs):
        calls.append({"state": state, **kwargs})
        return SimpleNamespace(
            content=(
                '{"candidates":[{"summary":"bounded candidate",'
                '"proposed_action":"continue safely",'
                '"predicted_outcome":"bounded progress",'
                '"confidence":0.8,"evidence_ids":[],'
                '"assumptions":[],"risks":[],'
                '"expected_cost":0.0,"expected_latency_ms":1.0}]}'
            ),
            provider="dispatch-test",
            model="spy-model",
            request_id="request:dispatch",
        )

    runtime._model_call = fake_model_call
    state = SimpleNamespace(ledger=SimpleNamespace(get=lambda _evidence_id: None))
    generator = runtime._provider_specialist_generator(state)

    candidates = generator("bounded task", None, SpecialistRole.SOLVER, 1)

    assert len(calls) == 1
    assert calls[0]["state"] is state
    assert calls[0]["metadata"]["purpose"] == "deliberation:solver"
    assert len(candidates) == 1
    assert candidates[0].metadata["provider"] == "dispatch-test"
    assert candidates[0].metadata["model"] == "spy-model"



def test_frontier_uncertainty_uses_strongest_unresolved_signal() -> None:
    decision = SimpleNamespace(
        diagnostics=SimpleNamespace(
            normalized_entropy=0.40,
            action_disagreement=0.55,
            outcome_disagreement=0.25,
        ),
        consensus=SimpleNamespace(
            normalized_entropy=0.72,
            agreement=0.80,
        ),
    )

    value = AdaptiveJeevesRuntime._frontier_uncertainty(decision)

    assert value == 0.72


def test_adaptive_config_has_positive_stagnation_threshold() -> None:
    config = AdaptiveConfig()

    assert 0.0 < config.minimum_frontier_uncertainty_reduction < 1.0



def test_consensus_cannot_rescue_low_absolute_quality_or_grounding() -> None:
    first = _candidate(
        "weak-consensus-a",
        confidence=0.45,
        action="take the same unsupported action",
        outcome="unsupported outcome",
    )
    second = _candidate(
        "weak-consensus-b",
        confidence=0.44,
        action="take the same unsupported action",
        outcome="unsupported outcome",
    )
    search = _search(
        (
            first,
            _score(
                first,
                total=-0.20,
                evidence_quality=0.10,
                verifier=0.30,
                risk_penalty=0.10,
            ),
        ),
        (
            second,
            _score(
                second,
                total=-0.22,
                evidence_quality=0.10,
                verifier=0.30,
                risk_penalty=0.10,
            ),
        ),
    )

    decision = FrontierReasoningCoordinator().decide(search)

    assert decision.consensus is not None
    assert decision.consensus.selected_candidate_id in {
        "candidate:weak-consensus-a",
        "candidate:weak-consensus-b",
    }
    assert EscalationCause.LOW_ABSOLUTE_QUALITY in decision.causes
    assert EscalationCause.INSUFFICIENT_EVIDENCE in decision.causes
    assert decision.disposition is not InferenceDisposition.COMMIT



def test_eval_gated_policy_tuning_promotes_useful_extra_compute_safely() -> None:
    coordinator = FrontierReasoningCoordinator()
    feedback = FrontierReasoningFeedback()
    for index in range(6):
        feedback.observe(
            coordinator.decide(_strong_search(trace=f"direct:{index}")),
            verified_success=False,
            escalation_rounds=0,
            model_calls=2,
            estimated_tokens=1000,
        )
        feedback.observe(
            coordinator.decide(_strong_search(trace=f"escalated:{index}")),
            verified_success=True,
            escalation_rounds=1,
            model_calls=5,
            estimated_tokens=3000,
        )

    recommendation = feedback.recommendation()
    assert recommendation.maximum_entropy_delta < 0.0

    eval_feedback = FrontierEvalFeedback()
    for index in range(8):
        eval_feedback.observe(
            EvalResult(
                case_id=f"case:tune-{index}",
                run_id=f"run:baseline-tune-{index}",
                score=0.70,
                passed=True,
                checks=(),
                result_fingerprint=stable_fingerprint({"baseline-tune": index}),
            ),
            EvalResult(
                case_id=f"case:tune-{index}",
                run_id=f"run:frontier-tune-{index}",
                score=0.82,
                passed=True,
                checks=(),
                result_fingerprint=stable_fingerprint({"frontier-tune": index}),
            ),
        )
    gate = eval_feedback.promotion_gate(
        minimum_cases=8,
        minimum_mean_delta=0.05,
        maximum_loss_rate=0.0,
        allow_pass_losses=0,
    )

    trial_evaluator = FrontierTrialEvaluator()
    for case_index in range(2):
        case_id = f"case:tune-passk-{case_index}"
        for trial_index in range(2):
            baseline_passed = trial_index == 0
            trial_evaluator.observe(
                EvalResult(
                    case_id=case_id,
                    run_id=f"run:tune-baseline-{case_index}-{trial_index}",
                    score=0.80 if baseline_passed else 0.50,
                    passed=baseline_passed,
                    checks=(),
                    result_fingerprint=stable_fingerprint(
                        {"tune-baseline": case_index, "trial": trial_index}
                    ),
                ),
                variant="baseline",
                model_calls=2,
                estimated_tokens=1000,
            )
            trial_evaluator.observe(
                EvalResult(
                    case_id=case_id,
                    run_id=f"run:tune-frontier-{case_index}-{trial_index}",
                    score=0.85,
                    passed=True,
                    checks=(),
                    result_fingerprint=stable_fingerprint(
                        {"tune-frontier": case_index, "trial": trial_index}
                    ),
                ),
                variant="frontier",
                model_calls=5,
                estimated_tokens=3000,
            )
    trial_comparison = trial_evaluator.compare(k=1)
    trial_gate = trial_evaluator.promotion_gate(
        trial_comparison,
        minimum_cases=2,
        minimum_pass_at_k_delta=0.25,
        minimum_mean_score_delta=0.0,
        maximum_regression_rate=0.0,
    )

    baseline = FrontierReasoningPolicy()
    blocked_without_trials = FrontierPolicyTuner().propose(
        baseline,
        recommendation,
        gate,
    )
    proposal = FrontierPolicyTuner().propose(
        baseline,
        recommendation,
        gate,
        trial_gate=trial_gate,
        feedback_report=feedback.report(),
    )

    assert blocked_without_trials.approved_for_trial is False
    assert any(
        "pass@k" in reason for reason in blocked_without_trials.reasons
    )
    assert trial_gate.passed is True
    assert proposal.approved_for_trial is True
    assert proposal.feedback_report_fingerprint == feedback.report().fingerprint
    assert proposal.trial_gate_fingerprint == trial_gate.fingerprint
    assert proposal.proposed_policy.maximum_normalized_entropy < baseline.maximum_normalized_entropy
    assert proposal.proposed_policy.verification_required_at is baseline.verification_required_at
    assert (
        proposal.proposed_policy.minimum_verification_lower_bound
        == baseline.minimum_verification_lower_bound
    )
    assert (
        proposal.proposed_policy.block_on_verifier_abstention
        == baseline.block_on_verifier_abstention
    )



def test_policy_tuning_is_blocked_without_matched_eval_gate() -> None:
    coordinator = FrontierReasoningCoordinator()
    feedback = FrontierReasoningFeedback()
    for index in range(6):
        feedback.observe(
            coordinator.decide(_strong_search(trace=f"blocked-direct:{index}")),
            verified_success=False,
            escalation_rounds=0,
            model_calls=2,
            estimated_tokens=1000,
        )
        feedback.observe(
            coordinator.decide(_strong_search(trace=f"blocked-escalated:{index}")),
            verified_success=True,
            escalation_rounds=1,
            model_calls=5,
            estimated_tokens=3000,
        )

    recommendation = feedback.recommendation()
    gate = FrontierEvalFeedback().promotion_gate(
        minimum_cases=1,
        minimum_mean_delta=0.0,
        maximum_loss_rate=1.0,
        allow_pass_losses=0,
    )
    baseline = FrontierReasoningPolicy()

    proposal = FrontierPolicyTuner().propose(
        baseline,
        recommendation,
        gate,
        feedback_report=feedback.report(),
    )

    assert gate.passed is False
    assert proposal.approved_for_trial is False
    assert proposal.proposed_policy == baseline
    assert proposal.changed_fields == {}



def test_repeated_trial_pass_at_k_measures_frontier_best_of_n_gain() -> None:
    evaluator = FrontierTrialEvaluator()
    for case_index in range(2):
        case_id = f"case:passk-{case_index}"
        for trial_index in range(4):
            baseline_passed = trial_index == 0
            frontier_passed = trial_index < 2
            evaluator.observe(
                EvalResult(
                    case_id=case_id,
                    run_id=f"run:baseline-passk-{case_index}-{trial_index}",
                    score=0.80 if baseline_passed else 0.50,
                    passed=baseline_passed,
                    checks=(),
                    result_fingerprint=stable_fingerprint(
                        {"baseline-passk": case_index, "trial": trial_index}
                    ),
                ),
                variant="baseline",
                model_calls=2,
                estimated_tokens=1000,
            )
            evaluator.observe(
                EvalResult(
                    case_id=case_id,
                    run_id=f"run:frontier-passk-{case_index}-{trial_index}",
                    score=0.85 if frontier_passed else 0.60,
                    passed=frontier_passed,
                    checks=(),
                    result_fingerprint=stable_fingerprint(
                        {"frontier-passk": case_index, "trial": trial_index}
                    ),
                ),
                variant="frontier",
                model_calls=5,
                estimated_tokens=3000,
            )

    baseline = evaluator.report(variant="baseline", k=2)
    frontier = evaluator.report(variant="frontier", k=2)
    comparison = evaluator.compare(k=2)
    gate = evaluator.promotion_gate(
        comparison,
        minimum_cases=2,
        minimum_pass_at_k_delta=0.20,
        minimum_mean_score_delta=0.0,
        maximum_regression_rate=0.0,
    )

    assert FrontierTrialEvaluator.empirical_pass_at_k(
        trials=4,
        successes=1,
        k=2,
    ) == 0.5
    assert baseline.mean_pass_at_k == 0.5
    assert frontier.mean_pass_at_k == 5.0 / 6.0
    assert comparison.pass_at_k_delta == (5.0 / 6.0) - 0.5
    assert comparison.incremental_model_calls == 3.0
    assert comparison.incremental_estimated_tokens == 2000.0
    assert comparison.regressed_cases == 0
    assert gate.passed is True



def test_policy_tuner_rejects_unbound_fabricated_recommendation() -> None:
    eval_feedback = FrontierEvalFeedback()
    eval_feedback.observe(
        EvalResult(
            case_id="case:fabricated-policy",
            run_id="run:fabricated-baseline",
            score=0.70,
            passed=True,
            checks=(),
            result_fingerprint=stable_fingerprint("fabricated-baseline"),
        ),
        EvalResult(
            case_id="case:fabricated-policy",
            run_id="run:fabricated-frontier",
            score=0.90,
            passed=True,
            checks=(),
            result_fingerprint=stable_fingerprint("fabricated-frontier"),
        ),
    )
    gate = eval_feedback.promotion_gate(
        minimum_cases=1,
        minimum_mean_delta=0.05,
        maximum_loss_rate=0.0,
        allow_pass_losses=0,
    )
    authoritative_feedback = FrontierReasoningFeedback()
    coordinator = FrontierReasoningCoordinator()
    for index in range(6):
        authoritative_feedback.observe(
            coordinator.decide(_strong_search(trace=f"authoritative-direct:{index}")),
            verified_success=False,
            escalation_rounds=0,
            model_calls=2,
            estimated_tokens=1000,
        )
        authoritative_feedback.observe(
            coordinator.decide(_strong_search(trace=f"authoritative-escalated:{index}")),
            verified_success=True,
            escalation_rounds=1,
            model_calls=5,
            estimated_tokens=3000,
        )
    report = authoritative_feedback.report()
    fabricated = FrontierFeedbackRecommendation(
        minimum_quality_delta=0.04,
        minimum_choice_probability_delta=0.03,
        maximum_entropy_delta=0.0,
        reasons=("fabricated recommendation",),
        fingerprint=stable_fingerprint("fabricated-recommendation"),
        feedback_report_fingerprint=stable_fingerprint("different-report"),
        sample_count=report.count,
        direct_count=report.direct_count,
        escalated_count=report.escalated_count,
    )
    baseline = FrontierReasoningPolicy()

    proposal = FrontierPolicyTuner().propose(
        baseline,
        fabricated,
        gate,
        feedback_report=report,
    )

    assert gate.passed is True
    assert proposal.approved_for_trial is False
    assert proposal.proposed_policy == baseline
    assert proposal.changed_fields == {}
    assert any("authoritative feedback report" in reason for reason in proposal.reasons)


def test_host_candidate_adjudicator_rewards_authoritative_diverse_evidence() -> None:
    ledger = EvidenceLedger(clock=lambda: 10.0)
    first = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:adjudicate-a",
            kind=EvidenceKind.FIXTURE,
            source="source:a",
            payload={"value": "a"},
            observed_at=1.0,
            confidence=0.92,
        )
    )
    second = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:adjudicate-b",
            kind=EvidenceKind.FIXTURE,
            source="source:b",
            payload={"value": "b"},
            observed_at=1.0,
            confidence=0.88,
        )
    )
    candidate = _candidate(
        "adjudicated-strong",
        confidence=0.90,
        action="use supported action",
        outcome="supported outcome",
        evidence=(first.ref, second.ref),
    )

    result = HostCandidateAdjudicator(ledger).adjudicate(candidate)

    assert result.score > 0.90
    assert result.custody_fraction == 1.0
    assert result.fingerprint_fraction == 1.0
    assert result.source_diversity == 1.0
    assert result.contradiction_count == 0
    assert result.known_evidence_count == 2


def test_host_candidate_adjudicator_penalizes_contradictions_and_bad_custody() -> None:
    ledger = EvidenceLedger(clock=lambda: 10.0)
    first = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:conflict-a",
            kind=EvidenceKind.FIXTURE,
            source="source:a",
            payload={"value": "a"},
            observed_at=1.0,
            confidence=0.95,
        )
    )
    second = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:conflict-b",
            kind=EvidenceKind.FIXTURE,
            source="source:b",
            payload={"value": "b"},
            observed_at=1.0,
            confidence=0.95,
        )
    )
    clean = _candidate(
        "clean-before-conflict",
        confidence=0.95,
        action="bounded action",
        outcome="bounded outcome",
        evidence=(first.ref, second.ref),
    )
    adjudicator = HostCandidateAdjudicator(ledger)
    clean_score = adjudicator.score(clean)

    ledger.mark_contradiction(
        first.evidence_id,
        second.evidence_id,
        "fixture contradiction",
    )
    conflicted = adjudicator.adjudicate(clean)

    bad_ref = EvidenceRef(
        evidence_id=first.evidence_id,
        kind=first.kind,
        source=first.source,
        fingerprint=stable_fingerprint({"wrong": "fingerprint"}),
        confidence=first.confidence,
        observed_at=first.observed_at,
    )
    unknown_ref = _evidence("missing-from-ledger", confidence=0.95)
    bad_custody = _candidate(
        "bad-custody",
        confidence=0.95,
        action="unsupported action",
        outcome="unsupported outcome",
        evidence=(bad_ref, unknown_ref),
    )
    bad = adjudicator.adjudicate(bad_custody)

    assert conflicted.score < clean_score
    assert conflicted.contradiction_count == 1
    assert conflicted.contradiction_rate == 1.0
    assert bad.score < conflicted.score
    assert bad.custody_fraction == 0.5
    assert bad.fingerprint_fraction == 0.0
    assert bad.known_evidence_count == 1
    assert any("unknown_evidence=" in reason for reason in bad.reasons)
    assert any("fingerprint_mismatch=" in reason for reason in bad.reasons)
