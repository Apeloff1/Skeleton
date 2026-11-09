from __future__ import annotations

import pytest

from skeleton.jeeves.agent.context_pipeline import LayeredContextResolver, ResolutionPolicy
from skeleton.jeeves.agent.interpretive_science import (
    LensOutcomeTrial,
    ScientificLensLab,
    ScientificLensPolicy,
    ScientificLensStatus,
)
from skeleton.jeeves.agent.lens_governance import LensPermission, ScientificGrade
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.nuance_runtime import NuanceRuntimeError, ScientificNuanceRuntime
from skeleton.jeeves.agent.relational_memory import RelationalMemoryIndex
from skeleton.jeeves.agent.semantic_governance import SemanticLensGovernanceBridge
from skeleton.jeeves.agent.semantic_lenses import LensFamily, SemanticFinding, SemanticObservation
from skeleton.jeeves.agent.semantic_frontier import FrontierLensRouter, FrontierSemanticRegistry
from skeleton.jeeves.agent.semantic_maximal import MaximalLensRouter, MaximalSemanticRegistry


def _runtime() -> tuple[MemoryNamespace, ScientificNuanceRuntime]:
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0))
    relations = RelationalMemoryIndex(cards)
    resolver = LayeredContextResolver(
        cards=cards,
        relations=relations,
        memory=MemoryManager(),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=1.0,
            stop_confidence=1.0,
            stop_trust=1.0,
        ),
    )
    return namespace, ScientificNuanceRuntime(resolver)


def test_semantic_governance_keeps_uncalibrated_lenses_in_shadow_mode() -> None:
    registry = FrontierSemanticRegistry()
    router = FrontierLensRouter(registry)
    observations = (
        SemanticObservation(
            "obs:1",
            "A montage cut juxtaposes a neutral face with a coffin.",
            0,
            tags=("film", "contrast"),
        ),
        SemanticObservation(
            "obs:2",
            "The same face is placed beside food and the reading changes.",
            1,
            tags=("film", "context"),
        ),
    )
    selection = router.select_frontier(
        observations,
        requested=("montage_collision",),
        max_lenses=8,
    )
    snapshot = SemanticLensGovernanceBridge().assess(selection, observations)
    record = snapshot.record_for("montage_collision")

    assert record is not None
    assert record.matched_cues
    assert record.decision.scientific_status is ScientificLensStatus.SHADOW
    assert LensPermission.HYPOTHESIS_GENERATION in record.decision.permissions
    assert LensPermission.FORECAST_GENERATION in record.decision.permissions
    assert record.decision.decision_feature_authorized is False
    assert record.decision.factual_assertion_authorized is False
    assert record.decision.causal_assertion_authorized is False
    assert 0.0 <= record.decision.predictive_weight <= 0.10


def test_semantic_profile_alias_reuses_empirical_kuleshov_governance() -> None:
    registry = FrontierSemanticRegistry()
    observations = (
        SemanticObservation("obs:a", "A neutral face appears before a meal.", 0),
        SemanticObservation("obs:b", "The same face appears after a coffin.", 1),
    )
    selection = FrontierLensRouter(registry).select_frontier(
        observations,
        requested=("kuleshov_context",),
        max_lenses=6,
    )
    record = SemanticLensGovernanceBridge().assess(
        selection,
        observations,
    ).record_for("kuleshov_context")

    assert record is not None
    assert record.decision.grade is ScientificGrade.EMPIRICAL
    assert record.decision.scientific_status is ScientificLensStatus.SHADOW
    assert record.decision.decision_feature_authorized is False
    assert record.decision.factual_assertion_authorized is False


def test_semantic_partial_observability_does_not_inherit_unverified_formal_authority() -> None:
    registry = FrontierSemanticRegistry()
    observations = (
        SemanticObservation(
            "obs:hidden",
            "The player acts under fog with hidden state and only partial observations.",
            0,
            tags=("game", "hidden-state"),
        ),
    )
    selection = FrontierLensRouter(registry).select_frontier(
        observations,
        requested=("fog_of_war_partial_observability",),
        max_lenses=6,
    )
    record = SemanticLensGovernanceBridge().assess(
        selection,
        observations,
    ).record_for("fog_of_war_partial_observability")

    assert record is not None
    assert record.decision.grade is ScientificGrade.INTERPRETIVE
    assert record.decision.decision_feature_authorized is False
    assert record.decision.factual_assertion_authorized is False


def test_extreme_lens_maturity_and_transfer_warning_survive_governance_bridge() -> None:
    registry = MaximalSemanticRegistry()
    observations = (
        SemanticObservation(
            "obs:scalar",
            "Some outcomes may be possible, but the stronger claim was not asserted.",
            0,
            tags=("pragmatics",),
        ),
    )
    selection = MaximalLensRouter(registry).select_maximal(
        observations,
        requested=("scalar_implicature",),
        max_lenses=8,
    )
    record = SemanticLensGovernanceBridge().assess(
        selection,
        observations,
    ).record_for("scalar_implicature")

    assert record is not None
    assert record.declared_maturity == "empirical"
    assert record.transfer_warning
    assert "Grice" in record.lineage
    assert record.decision.grade is ScientificGrade.INTERPRETIVE
    assert record.decision.factual_assertion_authorized is False
    assert record.decision.causal_assertion_authorized is False


def test_recorded_outcomes_raise_future_routing_weight_without_granting_truth() -> None:
    lab = ScientificLensLab(
        policy=ScientificLensPolicy(
            minimum_trials=2,
            minimum_independent_runs=2,
            minimum_domains_for_transfer=1,
            minimum_transfer_trials_per_domain=2,
            maximum_brier=0.25,
            maximum_ece=0.20,
            minimum_brier_gain_over_base_rate=0.01,
        )
    )
    for trial_id, probability, outcome, run in (
        ("good:1", 0.90, True, "run-1"),
        ("good:2", 0.10, False, "run-2"),
    ):
        lab.record(
            LensOutcomeTrial(
                trial_id=trial_id,
                lens_key="montage_collision",
                probability=probability,
                outcome=outcome,
                domain="film",
                independent_run=run,
                proposition="adjacent context changes the induced reading",
            )
        )

    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0))
    resolver = LayeredContextResolver(
        cards=cards,
        relations=RelationalMemoryIndex(cards),
        memory=MemoryManager(),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=1.0,
            stop_confidence=1.0,
            stop_trust=1.0,
        ),
    )
    runtime = ScientificNuanceRuntime(resolver, lens_lab=lab)
    runtime.prepare(namespace, "A neutral face is shown beside a meal.")
    frame = runtime.prepare(
        namespace,
        "A montage collision now cuts from the same neutral face to a coffin.",
        requested_lenses=("montage_collision",),
        capture_interaction=False,
    )
    record = frame.lens_governance.record_for("montage_collision")

    assert record is not None
    assert record.decision.scientific_status is ScientificLensStatus.ACTIVE
    assert record.decision.predictive_weight > 0.10
    assert record.decision.factual_assertion_authorized is False
    assert record.decision.causal_assertion_authorized is False


def test_governance_snapshot_identity_includes_semantic_domain() -> None:
    observations = (
        SemanticObservation(
            "obs:domain",
            "A montage contrast changes the contextual reading.",
            0,
            tags=("contrast",),
        ),
        SemanticObservation(
            "obs:domain:2",
            "A second image supplies the comparison.",
            1,
            tags=("film",),
        ),
    )
    registry = FrontierSemanticRegistry()
    selection = FrontierLensRouter(registry).select_frontier(
        observations,
        requested=("montage_collision",),
        max_lenses=6,
    )
    bridge = SemanticLensGovernanceBridge()
    film = bridge.assess(selection, observations, domain="film")
    game = bridge.assess(selection, observations, domain="game")

    assert film.domain == "film"
    assert game.domain == "game"
    assert film.fingerprint != game.fingerprint


def test_domain_scoped_weight_caps_unseen_transfer_without_erasing_global_calibration() -> None:
    policy = ScientificLensPolicy(
        minimum_trials=4,
        minimum_independent_runs=2,
        minimum_domains_for_transfer=2,
        minimum_transfer_trials_per_domain=2,
        maximum_brier=0.25,
        maximum_ece=0.20,
        minimum_brier_gain_over_base_rate=0.01,
    )
    lab = ScientificLensLab(policy=policy)
    for trial_id, p, outcome, domain, run in (
        ("film:1", 0.90, True, "film", "r1"),
        ("film:2", 0.10, False, "film", "r2"),
        ("dialogue:1", 0.85, True, "dialogue", "r1"),
        ("dialogue:2", 0.15, False, "dialogue", "r2"),
    ):
        lab.record(
            LensOutcomeTrial(
                trial_id=trial_id,
                lens_key="montage_collision",
                probability=p,
                outcome=outcome,
                domain=domain,
                independent_run=run,
                proposition="adjacent context changes the reading",
            )
        )

    observations = (
        SemanticObservation(
            "obs:1",
            "A montage collision juxtaposes a face and a coffin.",
            0,
            tags=("film",),
        ),
        SemanticObservation(
            "obs:2",
            "A second shot changes the contextual reading.",
            1,
            tags=("contrast",),
        ),
    )
    registry = FrontierSemanticRegistry()
    selection = FrontierLensRouter(registry).select_frontier(
        observations,
        requested=("montage_collision",),
        max_lenses=6,
    )
    bridge = SemanticLensGovernanceBridge(lab=lab)
    observed = bridge.assess(
        selection,
        observations,
        domain="film",
    ).record_for("montage_collision")
    unseen = bridge.assess(
        selection,
        observations,
        domain="game",
    ).record_for("montage_collision")

    assert observed is not None
    assert unseen is not None
    assert observed.decision.scientific_status is ScientificLensStatus.ACTIVE
    assert observed.domain_status == "observed"
    assert observed.domain_predictive_weight is not None
    assert observed.domain_predictive_weight > 0.10
    assert unseen.decision.predictive_weight == observed.decision.predictive_weight
    assert unseen.domain_status == "unseen"
    assert unseen.domain_predictive_weight is not None
    assert unseen.domain_predictive_weight <= 0.10


def test_nuance_frame_carries_governance_for_selected_lenses() -> None:
    namespace, runtime = _runtime()
    runtime.prepare(namespace, "Earlier a narrator insists the warning was false.")
    frame = runtime.prepare(
        namespace,
        "A montage contrast reframes the narrator claim.",
        requested_lenses=("montage_collision", "unreliable_narrator"),
        capture_interaction=False,
    )

    assert frame.lens_governance is not None
    assert frame.lens_governance.fingerprint
    assert frame.lens_governance.record_for("montage_collision") is not None
    assert frame.lens_governance.record_for("unreliable_narrator") is not None
    assert all(
        record.decision.factual_assertion_authorized is False
        for record in frame.lens_governance.records
    )


def test_registered_findings_build_calibration_weighted_semantic_hypergraph() -> None:
    namespace, runtime = _runtime()
    runtime.prepare(
        namespace,
        "A narrator claims the room is safe while a neutral face is shown.",
    )
    frame = runtime.prepare(
        namespace,
        "A montage juxtaposition cuts from the neutral face to a coffin, contradicting the narrator.",
        requested_lenses=("montage_collision", "unreliable_narrator"),
        capture_interaction=False,
    )
    assert len(frame.observations) >= 2
    observation_ids = tuple(item.observation_id for item in frame.observations[:2])
    findings = (
        SemanticFinding(
            finding_id="finding:montage",
            lens_key="montage_collision",
            family=LensFamily.FILM,
            observation_ids=observation_ids,
            interpretation="The juxtaposition supports a contrast reading.",
            prediction="Changing the adjacent image should change the induced reading.",
            confidence=0.82,
            ambiguity=0.22,
            novelty=0.72,
        ),
        SemanticFinding(
            finding_id="finding:narrator",
            lens_key="unreliable_narrator",
            family=LensFamily.LITERATURE,
            observation_ids=observation_ids,
            interpretation="The narrated claim conflicts with independent framing cues.",
            prediction="Later independent observations should diverge from the narrator claim.",
            confidence=0.78,
            ambiguity=0.28,
            novelty=0.61,
        ),
    )

    update = runtime.register_findings(frame, findings, sequence=1)

    assert update.hypergraph is not None
    assert update.hypergraph.fingerprint
    assert update.hypergraph.edges
    assert any(len(edge.families) >= 2 for edge in update.hypergraph.edges)
    assert all(edge.metadata["interpretive_only"] is True for edge in update.hypergraph.edges)
    assert all(edge.metadata["may_promote_to_evidence"] is False for edge in update.hypergraph.edges)
    assert all(0.0 <= edge.calibration_support <= 0.10 for edge in update.hypergraph.edges)


def test_resolved_semantic_forecast_feeds_lens_science_ledger() -> None:
    namespace, runtime = _runtime()
    runtime.prepare(namespace, "Earlier a neutral face appeared after a warning.")
    frame = runtime.prepare(
        namespace,
        "A montage contrast places the same face beside a coffin.",
        requested_lenses=("montage_collision",),
        capture_interaction=False,
    )
    observation_ids = tuple(item.observation_id for item in frame.observations[:2])
    finding = SemanticFinding(
        finding_id="finding:calibration",
        lens_key="montage_collision",
        family=LensFamily.FILM,
        observation_ids=observation_ids,
        interpretation="The adjacent image changes the plausible reading.",
        prediction="A changed adjacent image will change the interpretation.",
        confidence=0.84,
        ambiguity=0.20,
        novelty=0.70,
    )
    update = runtime.register_findings(frame, (finding,), sequence=2)
    forecast = next(
        item
        for item in update.forecasts
        if item.source_finding_ids == (finding.finding_id,)
    )

    open_fingerprint = forecast.fingerprint
    resolved = runtime.resolve_forecast(
        forecast.forecast_id,
        outcome=True,
        domain="film",
        independent_run="run-1",
        observation_id="observed:later",
    )

    assert resolved.outcome is True
    trials = runtime.lens_lab.trials("montage_collision")
    assert len(trials) == 1
    assert trials[0].source_finding_id == finding.finding_id
    assert trials[0].source_forecast_id == forecast.forecast_id
    assert trials[0].source_forecast_fingerprint == open_fingerprint
    assert trials[0].domain == "film"
    summary = runtime.lens_science_summary()
    assert summary["resolved_forecasts"] == 1
    assert summary["calibrated_lens_count"] == 1
    assert summary["lens_statuses"]["montage_collision"] == "shadow"
    assert summary["hypergraph_count"] == 1
    assert summary["invariants"]["semantic_lenses_remain_interpretive"] is True


def test_resolve_forecast_requires_complete_calibration_identity() -> None:
    namespace, runtime = _runtime()
    runtime.prepare(namespace, "Earlier context.")
    frame = runtime.prepare(
        namespace,
        "A montage contrast changes the context.",
        requested_lenses=("montage_collision",),
        capture_interaction=False,
    )
    observation_ids = tuple(item.observation_id for item in frame.observations[:2])
    finding = SemanticFinding(
        finding_id="finding:identity",
        lens_key="montage_collision",
        family=LensFamily.FILM,
        observation_ids=observation_ids,
        interpretation="Contrast reading.",
        prediction="The next paired context changes the reading.",
        confidence=0.75,
        ambiguity=0.30,
        novelty=0.50,
    )
    update = runtime.register_findings(frame, (finding,), sequence=3)
    forecast = next(item for item in update.forecasts if item.source_finding_ids)

    with pytest.raises(NuanceRuntimeError, match="domain and independent_run"):
        runtime.resolve_forecast(
            forecast.forecast_id,
            outcome=True,
            domain="film",
        )
