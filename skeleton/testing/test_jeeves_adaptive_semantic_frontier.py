from __future__ import annotations

import pytest

from skeleton.jeeves.agent.adaptive_runtime import (
    AdaptiveJeevesRuntime,
    AdaptiveRuntimeError,
)
from skeleton.jeeves.agent.deliberation import (
    CandidateProposal,
    CandidateScore,
    DeliberationMode,
    SearchResult,
    SpecialistRole,
)
from skeleton.jeeves.agent.frontier_reasoning import (
    EscalationCause,
    FrontierReasoningCoordinator,
    InferenceDisposition,
)
from skeleton.jeeves.agent.lens_fusion import LensSignal
from skeleton.jeeves.agent.provider import (
    DeterministicProvider,
    ProviderRouter,
)
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.semantic_frontier import LensInteractionKind
from skeleton.jeeves.agent.semantic_lenses import (
    LensFamily,
    SemanticFinding,
    SemanticObservation,
)
from skeleton.jeeves.agent.types import Goal, RiskTier, stable_fingerprint


class TickClock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


def _runtime(clock: TickClock) -> AdaptiveJeevesRuntime:
    provider = DeterministicProvider(("unused",))
    return AdaptiveJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )


def _inputs(run_id: str) -> RunInputs:
    return RunInputs(
        goal=Goal(
            "goal-semantic-frontier",
            "Produce a bounded evidence-aware answer.",
            success_criteria=(
                "Semantic interpretation must not manufacture evidence.",
            ),
        ),
        tenant_id="tenant-semantic-frontier",
        user_id="user-semantic-frontier",
        workspace_id="workspace-semantic-frontier",
        session_id="session-semantic-frontier",
        run_id=run_id,
    )


def _observations() -> tuple[SemanticObservation, ...]:
    return (
        SemanticObservation(
            "semantic-advisory-o1",
            (
                "The deployment distribution may have shifted while a common "
                "cause still confounds the observed association."
            ),
            0,
            evidence_ids=("semantic-ev-1",),
            tags=("shift", "confound"),
        ),
        SemanticObservation(
            "semantic-advisory-o2",
            (
                "A later independent observation can distinguish concept drift "
                "from a stable causal relation."
            ),
            1,
            evidence_ids=("semantic-ev-2",),
            tags=("drift", "independent"),
        ),
    )


def _finding(
    finding_id: str,
    lens_key: str,
    family: LensFamily,
    *,
    confidence: float,
    ambiguity: float,
) -> SemanticFinding:
    return SemanticFinding(
        finding_id=finding_id,
        lens_key=lens_key,
        family=family,
        observation_ids=(
            "semantic-advisory-o1",
            "semantic-advisory-o2",
        ),
        interpretation=(
            f"{lens_key} is one bounded interpretation of the observations."
        ),
        prediction=(
            f"An independent later observation can discriminate {lens_key}."
        ),
        confidence=confidence,
        ambiguity=ambiguity,
        novelty=0.7,
        evidence_ids=("semantic-ev-1", "semantic-ev-2"),
        metadata={"adaptive_semantic_test": True},
    )


def _snapshot(runtime: AdaptiveJeevesRuntime):
    return runtime.semantic_plane.analyze(
        _observations(),
        findings=(
            _finding(
                "semantic-advisory-drift",
                "concept_drift",
                LensFamily.PREDICTIVE,
                confidence=0.88,
                ambiguity=0.12,
            ),
            _finding(
                "semantic-advisory-confound",
                "backdoor_confounding",
                LensFamily.CAUSAL,
                confidence=0.82,
                ambiguity=0.18,
            ),
        ),
        requested=("concept_drift", "backdoor_confounding"),
        base_rate=0.5,
    )


def test_semantic_reasoning_signals_are_escalation_only_and_in_custody() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    snapshot = _snapshot(runtime)

    signals = runtime.semantic_plane.reasoning_signals(snapshot)

    assert signals
    assert all(
        item.metadata["inference_authority"] == "escalation_only"
        for item in signals
    )
    assert all(
        item.metadata["may_increase_evidence_quality"] is False
        for item in signals
    )
    assert all(
        item.metadata["may_authorize_commit"] is False
        for item in signals
    )
    assert all(
        runtime.semantic_plane.reasoning_signal_is_current(item)
        for item in signals
    )

    first = signals[0]
    runtime.semantic_plane.resolve_forecast(
        first.signal_id,
        outcome=True,
        domain="adaptive-semantic",
        independent_run="adaptive-semantic-resolution",
    )

    assert runtime.semantic_plane.reasoning_signal_is_current(first) is False
    refreshed = runtime.semantic_plane.reasoning_signals(snapshot)
    assert first.signal_id not in {
        item.signal_id for item in refreshed
    }


def test_adaptive_runtime_binds_semantic_snapshot_to_live_run() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-semantic-bind")
    state = runtime._new_state(inputs.run_id, inputs)
    snapshot = _snapshot(runtime)

    signals = runtime.bind_semantic_reasoning_snapshot(
        state.run_id,
        snapshot,
    )
    routed = runtime._semantic_frontier_signals(state)

    assert signals
    assert [item.signal_id for item in routed] == [
        item.signal_id for item in signals
    ]
    advisory = state.scratch.get("semantic:frontier_advisory")
    assert advisory is not None
    assert advisory["authority"] == "escalation_only"
    assert advisory["may_increase_evidence_quality"] is False
    assert advisory["may_authorize_commit"] is False
    assert advisory["signal_count"] == len(routed)


def test_semantic_snapshot_cannot_bind_to_unknown_adaptive_run() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    snapshot = _snapshot(runtime)

    with pytest.raises(
        AdaptiveRuntimeError,
        match="missing adaptive state",
    ):
        runtime.bind_semantic_reasoning_snapshot(
            "run-that-does-not-exist",
            snapshot,
        )


def test_topology_learning_revision_invalidates_bound_semantic_advisory() -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-semantic-stale")
    state = runtime._new_state(inputs.run_id, inputs)
    snapshot = _snapshot(runtime)
    runtime.bind_semantic_reasoning_snapshot(state.run_id, snapshot)

    scoped_plane = runtime.semantic_plane_for(inputs)
    candidate = scoped_plane.topology.bridge_candidates(
        limit=1,
        minimum_score=0.0,
    )[0]
    runtime.declare_scoped_semantic_topology_candidate_prediction(
        inputs,
        candidate.candidate_id,
        kind=LensInteractionKind.REINFORCES,
        predicted_probability=0.70,
        domain="film",
        independent_run="semantic-advisory-drift",
        predicted_at=clock(),
    )

    assert runtime._semantic_frontier_signals(state) == ()
    assert runtime.clear_semantic_reasoning_snapshot(state.run_id) is False


def _candidate_search() -> SearchResult:
    candidate = CandidateProposal(
        candidate_id="candidate-safe",
        parent_id=None,
        depth=0,
        role=SpecialistRole.SOLVER,
        summary="Use the bounded read-only answer.",
        proposed_action="Return the bounded read-only answer.",
        predicted_outcome="The user receives the bounded answer.",
        confidence=0.95,
        evidence=(),
        assumptions=(),
        risks=(),
    )
    score = CandidateScore(
        candidate_id=candidate.candidate_id,
        utility=0.95,
        evidence_quality=0.90,
        confidence_quality=0.95,
        risk_penalty=0.0,
        cost_penalty=0.0,
        novelty_bonus=0.1,
        verifier_score=0.95,
        total=0.95,
    )
    return SearchResult(
        mode=DeliberationMode.DELIBERATE,
        best=candidate,
        ranking=((candidate, score),),
        explored=(candidate,),
        ledger={"model_calls": 1, "estimated_tokens": 128},
        stopped_reason="bounded-test",
        trace_fingerprint=stable_fingerprint(
            {
                "candidate": candidate.fingerprint,
                "score": score.total,
            }
        ),
    )


def _conflicting_signals() -> tuple[LensSignal, LensSignal]:
    return (
        LensSignal(
            signal_id="semantic-pro",
            lens_key="concept_drift",
            family=LensFamily.PREDICTIVE,
            probability=0.95,
            confidence=1.0,
            ambiguity=0.0,
            reliability=1.0,
            epistemic_strength=1.0,
            calibration_group="semantic-pro",
            metadata={
                "inference_authority": "escalation_only",
                "may_increase_evidence_quality": False,
                "may_authorize_commit": False,
            },
        ),
        LensSignal(
            signal_id="semantic-counter",
            lens_key="backdoor_confounding",
            family=LensFamily.CAUSAL,
            probability=0.05,
            confidence=1.0,
            ambiguity=0.0,
            reliability=1.0,
            epistemic_strength=1.0,
            calibration_group="semantic-counter",
            metadata={
                "inference_authority": "escalation_only",
                "may_increase_evidence_quality": False,
                "may_authorize_commit": False,
            },
        ),
    )


def test_semantic_conflict_can_escalate_but_cannot_improve_evidence_quality() -> None:
    coordinator = FrontierReasoningCoordinator()
    search = _candidate_search()

    baseline = coordinator.decide(
        search,
        risk=RiskTier.READ_ONLY,
    )
    semantic = coordinator.decide(
        search,
        risk=RiskTier.READ_ONLY,
        lens_signals=_conflicting_signals(),
    )

    assert baseline.disposition is InferenceDisposition.COMMIT
    assert semantic.disposition is InferenceDisposition.DELIBERATE
    assert EscalationCause.LENS_CONFLICT in semantic.causes
    assert semantic.lens_fusion is not None
    assert semantic.lens_fusion.conflict_strength > 0.5
    assert (
        semantic.assessments[0].evidence_quality
        == baseline.assessments[0].evidence_quality
        == 0.90
    )
    assert semantic.assessments[0].absolute_quality == (
        baseline.assessments[0].absolute_quality
    )


def test_semantic_compute_pressure_is_monotonic_and_does_not_touch_evidence(
    monkeypatch,
) -> None:
    clock = TickClock()
    runtime = _runtime(clock)
    inputs = _inputs("run-semantic-compute")
    state = runtime._new_state(inputs.run_id, inputs)

    baseline = runtime._compute_signals(
        state,
        purpose="reasoning-step",
    )
    evidence_before = state.ledger.fingerprint

    monkeypatch.setattr(
        runtime,
        "_semantic_frontier_signals",
        lambda _state: _conflicting_signals(),
    )
    pressured = runtime._compute_signals(
        state,
        purpose="reasoning-step",
    )

    assert pressured.uncertainty >= baseline.uncertainty
    assert pressured.contradiction >= baseline.contradiction
    assert (
        pressured.expected_information_gain
        >= baseline.expected_information_gain
    )
    assert state.ledger.fingerprint == evidence_before
    assert state.ledger.artifacts() == ()


class _SemanticDriveProbeRuntime(AdaptiveJeevesRuntime):
    def _drive(self, state):
        signals = self._semantic_frontier_signals(state)
        assert signals
        assert state.scratch.get("semantic:frontier_advisory") is not None
        return {
            "run_id": state.run_id,
            "signal_ids": tuple(item.signal_id for item in signals),
        }

    def _post_run(self, inputs, result):
        return result


def test_run_with_semantics_binds_advisory_before_drive() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = _SemanticDriveProbeRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    inputs = _inputs("run-with-semantics")

    result = runtime.run_with_semantics(
        inputs,
        _observations(),
        findings=(
            _finding(
                "run-with-semantics-drift",
                "concept_drift",
                LensFamily.PREDICTIVE,
                confidence=0.88,
                ambiguity=0.12,
            ),
        ),
        requested=("concept_drift",),
        base_rate=0.5,
    )

    assert result["run_id"] == inputs.run_id
    assert result["signal_ids"]
    scoped_plane = runtime.semantic_plane_for(inputs)
    assert scoped_plane is not runtime.semantic_plane
    assert scoped_plane.prediction_ledger.open_forecasts()


def test_lens_conflict_contributes_to_adaptive_frontier_uncertainty() -> None:
    coordinator = FrontierReasoningCoordinator()
    decision = coordinator.decide(
        _candidate_search(),
        risk=RiskTier.READ_ONLY,
        lens_signals=_conflicting_signals(),
    )

    uncertainty = AdaptiveJeevesRuntime._frontier_uncertainty(decision)

    assert decision.lens_fusion is not None
    assert uncertainty >= decision.lens_fusion.conflict_strength
