from __future__ import annotations

from skeleton.jeeves.agent.lens_fusion import (
    LensDependenceKind,
    LensFusionEngine,
    LensSignal,
)
from skeleton.jeeves.agent.interpretive_science import (
    LensOutcomeTrial,
    ScientificLensLab,
    ScientificLensPolicy,
    ScientificLensStatus,
)
from skeleton.jeeves.agent.lens_governance import (
    LensPermission,
    LensScienceRegistry,
    ScientificGrade,
)
from skeleton.jeeves.agent.lens_hypergraph import SemanticLensHypergraph
from skeleton.jeeves.agent.semantic_governance_bridge import SemanticGovernanceBridge
from skeleton.jeeves.agent.semantic_lenses import (
    LensFamily,
    ReadingStatus,
    SemanticFinding,
    SemanticObservation,
    SemanticRole,
)
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry
from skeleton.jeeves.agent.semantic_plane import SemanticLensPlane, SemanticPlanePolicy
from skeleton.jeeves.agent.semantic_plane_interactions import plane_interaction_rules
from skeleton.jeeves.agent.semantic_plane_lenses import (
    plane_catalog_fingerprint,
    plane_definitions_by_family,
    plane_semantic_definitions,
    plane_semantic_specs,
)


PLANE_FAMILIES = {
    LensFamily.CAUSAL,
    LensFamily.INFORMATION,
    LensFamily.COMPUTATIONAL,
    LensFamily.METACOGNITIVE,
    LensFamily.PROBABILITY,
    LensFamily.PREDICTIVE,
}


def _observations() -> tuple[SemanticObservation, ...]:
    return (
        SemanticObservation(
            "plane-o1",
            (
                "A common cause may confound the association while the target domain "
                "shows covariate shift. The model has structural model uncertainty "
                "and aleatoric epistemic uncertainty."
            ),
            0,
            evidence_ids=("ev-1",),
            tags=("confound", "covariate shift", "model uncertainty"),
        ),
        SemanticObservation(
            "plane-o2",
            (
                "A diagnostic positive occurs in a rare population. We can acquire "
                "another observation for value of information, but the search state "
                "space is combinatorial and expensive."
            ),
            1,
            evidence_ids=("ev-2",),
            tags=("base rate", "value of information", "state space"),
        ),
        SemanticObservation(
            "plane-o3",
            (
                "A leading indicator moves before the outcome, but reverse causality "
                "and a regime switch remain plausible."
            ),
            2,
            evidence_ids=("ev-3",),
            tags=("leading", "reverse causality", "regime"),
        ),
    )


def _finding(
    finding_id: str,
    lens_key: str,
    family: LensFamily,
    *,
    confidence: float = 0.82,
    ambiguity: float = 0.18,
) -> SemanticFinding:
    return SemanticFinding(
        finding_id=finding_id,
        lens_key=lens_key,
        family=family,
        observation_ids=("plane-o1", "plane-o2"),
        interpretation=f"{lens_key} is a candidate reading of the current observations.",
        prediction=f"A discriminating future observation should test {lens_key}.",
        confidence=confidence,
        ambiguity=ambiguity,
        novelty=0.65,
        evidence_ids=("ev-1", "ev-2"),
        counterreading="",
        metadata={"test_fixture": True},
    )


def test_plane_catalog_adds_six_deep_families_with_balanced_coverage() -> None:
    definitions = plane_semantic_definitions()
    specs = plane_semantic_specs()
    grouped = plane_definitions_by_family(definitions)
    keys = [item.spec.key for item in definitions]

    assert len(definitions) == 48
    assert len(specs) == 48
    assert len(keys) == len(set(keys))
    assert set(grouped) == PLANE_FAMILIES
    assert all(len(grouped[family]) == 8 for family in PLANE_FAMILIES)
    assert all(item.spec.rare for item in definitions)
    assert all(item.lineage for item in definitions)
    assert all(item.transfer_warning for item in definitions)
    assert len(plane_catalog_fingerprint()) == 64


def test_maximal_registry_contains_full_semantic_plane_without_key_collisions() -> None:
    registry = MaximalSemanticRegistry()
    all_specs = registry.all()
    keys = [item.key for item in all_specs]

    assert len(keys) == len(set(keys))
    assert {item.family for item in all_specs}.issuperset(PLANE_FAMILIES)
    assert {
        "backdoor_confounding",
        "mutual_information_gain",
        "concurrency_interleaving",
        "hypothesis_lockin",
        "sequential_evidence_accumulation",
        "concept_drift",
    }.issubset(set(keys))


def test_semantic_governance_bridge_preserves_evidence_ceiling() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=40,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )
    observations = _observations()
    selection = plane.select(
        observations,
        requested=(
            "backdoor_confounding",
            "mutual_information_gain",
            "concurrency_interleaving",
        ),
    )
    snapshot = SemanticGovernanceBridge().assess(
        selection,
        observations=observations,
    )

    causal = snapshot.decision_for("backdoor_confounding")
    assert causal is not None
    assert causal.grade is ScientificGrade.FORMAL
    assert LensPermission.HYPOTHESIS_GENERATION in causal.permissions
    assert LensPermission.FORECAST_GENERATION in causal.permissions
    assert causal.factual_assertion_authorized is False
    assert causal.causal_assertion_authorized is False
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False
    assert 0.0 <= snapshot.weight_for("backdoor_confounding") <= 1.0


def test_cross_plane_interaction_rules_are_unique_and_deep() -> None:
    rules = plane_interaction_rules()
    keys = [rule.key for rule in rules]

    assert len(rules) == 30
    assert len(keys) == len(set(keys))
    assert any(
        rule.key == tuple(sorted(("backdoor_confounding", "covariate_shift")))
        for rule in rules
    )
    assert any(
        rule.key == tuple(sorted(("hypothesis_lockin", "confirmation_search_bias")))
        for rule in rules
    )
    assert any(
        rule.key == tuple(sorted(("queue_backpressure", "forecast_horizon_decay")))
        for rule in rules
    )


def test_hypergraph_diversity_is_intrinsic_not_catalog_size_dependent() -> None:
    findings = (
        _finding("hyper-causal", "backdoor_confounding", LensFamily.CAUSAL),
        _finding("hyper-predictive", "covariate_shift", LensFamily.PREDICTIVE),
    )
    snapshot = SemanticLensHypergraph().build(
        findings,
        calibration_weights={
            "backdoor_confounding": 1.0,
            "covariate_shift": 1.0,
        },
    )

    assert snapshot.edges
    assert any(
        set(edge.families) == {LensFamily.CAUSAL, LensFamily.PREDICTIVE}
        and edge.family_diversity == 1.0
        for edge in snapshot.edges
    )


def test_semantic_plane_rejects_contract_mismatched_findings() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=32,
            max_per_family=5,
            minimum_rare_when_supported=2,
        )
    )
    observations = _observations()
    selection = plane.select(
        observations,
        requested=("backdoor_confounding",),
    )
    findings = (
        _finding("valid", "backdoor_confounding", LensFamily.CAUSAL),
        _finding("wrong-family", "backdoor_confounding", LensFamily.FILM),
        _finding("unknown", "not_a_real_lens", LensFamily.SYSTEM),
        SemanticFinding(
            finding_id="orphan",
            lens_key="backdoor_confounding",
            family=LensFamily.CAUSAL,
            observation_ids=("not-current",),
            interpretation="Orphan interpretation.",
            prediction="Orphan prediction.",
            confidence=0.8,
            ambiguity=0.2,
            novelty=0.5,
        ),
    )

    audit = plane.audit_findings(
        findings,
        observations=observations,
        selection=selection,
    )

    assert [item.finding_id for item in audit.accepted] == ["valid"]
    rejected = {item.finding_id: set(item.reasons) for item in audit.rejected}
    assert "lens_family_mismatch" in rejected["wrong-family"]
    assert "unknown_lens_key" in rejected["unknown"]
    assert "no_overlap_with_current_observations" in rejected["orphan"]


def test_semantic_plane_executes_selection_governance_composition_prediction_and_fusion() -> None:
    requested = (
        "backdoor_confounding",
        "covariate_shift",
        "model_uncertainty_separation",
        "aleatoric_epistemic_split",
        "value_of_information",
        "state_space_explosion",
    )
    findings = (
        _finding("f-causal", "backdoor_confounding", LensFamily.CAUSAL),
        _finding("f-predictive", "covariate_shift", LensFamily.PREDICTIVE),
        _finding(
            "f-meta",
            "model_uncertainty_separation",
            LensFamily.METACOGNITIVE,
        ),
        _finding(
            "f-probability",
            "aleatoric_epistemic_split",
            LensFamily.PROBABILITY,
        ),
        _finding(
            "f-information",
            "value_of_information",
            LensFamily.INFORMATION,
        ),
        _finding(
            "f-computational",
            "state_space_explosion",
            LensFamily.COMPUTATIONAL,
        ),
    )
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=40,
            max_per_family=6,
            minimum_rare_when_supported=3,
            max_perpendicular_axes=12,
        )
    )

    snapshot = plane.analyze(
        _observations(),
        findings=findings,
        requested=requested,
        base_rate=0.4,
    )

    assert set(requested).issubset({item.key for item in snapshot.selection.lenses})
    assert len(snapshot.finding_audit.accepted) == len(findings)
    assert not snapshot.finding_audit.rejected
    assert len(snapshot.composition.interactions) >= 2
    assert snapshot.hypergraph.edges
    assert snapshot.forecasts
    assert snapshot.fusion.dependencies
    assert snapshot.coverage.accepted_findings == len(findings)
    assert snapshot.coverage.pairwise_interactions == len(snapshot.composition.interactions)
    assert snapshot.coverage.hyperedges == len(snapshot.hypergraph.edges)
    assert snapshot.tangent_ids
    assert snapshot.frontier.tangent_ids
    assert snapshot.coverage.tangent_count == len(snapshot.tangent_ids)
    assert snapshot.coverage.frontier_tangent_count == len(snapshot.frontier.tangent_ids)
    assert snapshot.coverage.family_coverage > 0.0
    assert snapshot.coverage.role_coverage > 0.0
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False
    assert len(snapshot.fingerprint) == 64


def test_semantic_plane_without_findings_abstains_instead_of_inventing_signal() -> None:
    plane = SemanticLensPlane()
    snapshot = plane.analyze(
        _observations(),
        requested=("backdoor_confounding", "concept_drift"),
    )

    assert not snapshot.finding_audit.accepted
    assert not snapshot.forecasts
    assert snapshot.fusion.abstain is True
    assert "no_signals" in snapshot.fusion.abstention_reasons
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False


def test_semantic_plane_resolution_feeds_scientific_calibration_ledger() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=32,
            max_per_family=5,
            minimum_rare_when_supported=2,
        )
    )
    finding = _finding(
        "learning-concept-drift",
        "concept_drift",
        LensFamily.PREDICTIVE,
    )
    contract_before = plane.fingerprint
    snapshot = plane.analyze(
        _observations(),
        findings=(finding,),
        requested=("concept_drift",),
    )
    forecast = next(
        item
        for item in snapshot.forecasts
        if item.source_finding_ids == ("learning-concept-drift",)
    )

    update = plane.resolve_forecast(
        forecast.forecast_id,
        outcome=True,
        domain="runtime-regression",
        independent_run="run-001",
    )

    assert update.calibrated_keys == ("concept_drift",)
    assert len(update.trial_ids) == 1
    assert len(update.reports) == 1
    report = update.reports[0]
    assert report.lens_key == "concept_drift"
    assert report.trial_count == 1
    assert report.independent_runs == 1
    trial = plane.governance.registry.lab.trials("concept_drift")[0]
    assert trial.source_forecast_id == forecast.forecast_id
    assert trial.source_forecast_fingerprint == forecast.fingerprint
    assert len(update.fingerprint) == 64
    assert plane.fingerprint == contract_before

    # The same ScientificLensLab is used by governance on the next plane pass,
    # closing the outcome -> calibration -> routing loop.
    next_selection = plane.select(
        _observations(),
        requested=("concept_drift",),
    )
    governed = plane.governance.assess(
        next_selection,
        observations=_observations(),
    )
    decision = governed.decision_for("concept_drift")
    assert decision is not None
    assert decision.scientific_status == report.status
    assert 0.0 <= decision.predictive_weight <= 1.0


def test_semantic_plane_domain_weight_caps_unseen_transfer() -> None:
    lab = ScientificLensLab(
        policy=ScientificLensPolicy(
            minimum_trials=4,
            minimum_independent_runs=2,
            minimum_domains_for_transfer=2,
            minimum_transfer_trials_per_domain=2,
            maximum_brier=0.25,
            maximum_ece=0.20,
            minimum_brier_gain_over_base_rate=0.01,
        )
    )
    for trial_id, p, outcome, domain, run in (
        ("drift:prod:1", 0.90, True, "production", "r1"),
        ("drift:prod:2", 0.10, False, "production", "r2"),
        ("drift:sim:1", 0.85, True, "simulation", "r1"),
        ("drift:sim:2", 0.15, False, "simulation", "r2"),
    ):
        lab.record(
            LensOutcomeTrial(
                trial_id=trial_id,
                lens_key="concept_drift",
                probability=p,
                outcome=outcome,
                domain=domain,
                independent_run=run,
                proposition="concept drift changes the predictive relation",
            )
        )
    bridge = SemanticGovernanceBridge(
        LensScienceRegistry(lab=lab)
    )
    plane = SemanticLensPlane(governance=bridge)
    finding = _finding(
        "domain-drift",
        "concept_drift",
        LensFamily.PREDICTIVE,
    )

    observed = plane.analyze(
        _observations(),
        findings=(finding,),
        requested=("concept_drift",),
        domain="production",
    )
    unseen = plane.analyze(
        _observations(),
        findings=(finding,),
        requested=("concept_drift",),
        domain="unseen-deployment",
    )

    observed_decision = observed.governance.decision_for("concept_drift")
    unseen_decision = unseen.governance.decision_for("concept_drift")
    assert observed_decision is not None
    assert unseen_decision is not None
    assert observed_decision.scientific_status is ScientificLensStatus.ACTIVE
    assert observed.governance.domain == "production"
    assert observed.governance.domain_status_for("concept_drift") == "observed"
    assert (
        observed.governance.weight_for("concept_drift")
        == observed.governance.global_weight_for("concept_drift")
    )
    assert unseen.governance.domain == "unseen-deployment"
    assert unseen.governance.domain_status_for("concept_drift") == "unseen"
    assert unseen.governance.weight_for("concept_drift") <= 0.10
    assert (
        unseen.governance.global_weight_for("concept_drift")
        == observed.governance.global_weight_for("concept_drift")
    )
    assert observed.governance.fingerprint != unseen.governance.fingerprint


def test_semantic_plane_target_fusion_never_pools_distinct_propositions() -> None:
    observations = _observations()
    plane = SemanticLensPlane()
    findings = (
        _finding(
            "target-causal",
            "backdoor_confounding",
            LensFamily.CAUSAL,
        ),
        _finding(
            "target-shift",
            "covariate_shift",
            LensFamily.PREDICTIVE,
        ),
    )
    snapshot = plane.analyze(
        observations,
        findings=findings,
        requested=("backdoor_confounding", "covariate_shift"),
    )
    finding_forecasts = {
        item.source_finding_ids[0]: item
        for item in snapshot.forecasts
        if len(item.source_finding_ids) == 1
    }
    left = finding_forecasts["target-causal"]
    right = finding_forecasts["target-shift"]

    assert plane._forecast_target_key(left) != plane._forecast_target_key(right)
    assert not any(
        {left.forecast_id, right.forecast_id}.issubset(
            set(group.forecast_ids)
        )
        for group in snapshot.target_fusions
    )


def test_semantic_plane_target_fusion_groups_identical_targets() -> None:
    observations = _observations()
    plane = SemanticLensPlane()
    shared_prediction = (
        "The next held-out observation will exhibit the same regime shift."
    )
    findings = (
        SemanticFinding(
            finding_id="same-target-causal",
            lens_key="backdoor_confounding",
            family=LensFamily.CAUSAL,
            observation_ids=("plane-o1", "plane-o2"),
            interpretation="Confounding is a candidate explanation.",
            prediction=shared_prediction,
            confidence=0.82,
            ambiguity=0.18,
            novelty=0.65,
            evidence_ids=("ev-1", "ev-2"),
        ),
        SemanticFinding(
            finding_id="same-target-shift",
            lens_key="covariate_shift",
            family=LensFamily.PREDICTIVE,
            observation_ids=("plane-o1", "plane-o2"),
            interpretation="Covariate shift is a candidate explanation.",
            prediction=shared_prediction,
            confidence=0.80,
            ambiguity=0.20,
            novelty=0.62,
            evidence_ids=("ev-1", "ev-2"),
        ),
    )
    snapshot = plane.analyze(
        observations,
        findings=findings,
        requested=("backdoor_confounding", "covariate_shift"),
    )
    ids = {
        item.forecast_id
        for item in snapshot.forecasts
        if set(item.source_finding_ids)
        & {"same-target-causal", "same-target-shift"}
    }
    grouped = [
        item
        for item in snapshot.target_fusions
        if ids.issubset(set(item.forecast_ids))
    ]

    assert len(ids) == 2
    assert len(grouped) == 1
    assert grouped[0].result.dependencies
    assert grouped[0].fingerprint
    assert snapshot.semantic_domain is None


def test_interaction_forecast_calibrates_composite_not_constituent_lenses_twice() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=36,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )
    findings = (
        _finding("interaction-causal", "backdoor_confounding", LensFamily.CAUSAL),
        _finding("interaction-shift", "covariate_shift", LensFamily.PREDICTIVE),
    )
    snapshot = plane.analyze(
        _observations(),
        findings=findings,
        requested=("backdoor_confounding", "covariate_shift"),
    )
    interaction_forecast = next(
        item
        for item in snapshot.forecasts
        if item.source_interaction_ids
        and set(item.source_lens_keys)
        == {"backdoor_confounding", "covariate_shift"}
    )

    update = plane.resolve_forecast(
        interaction_forecast.forecast_id,
        outcome=False,
        domain="integration",
        independent_run="interaction-run-001",
    )

    assert update.calibrated_keys == (
        "interaction:backdoor_confounding+covariate_shift",
    )
    assert plane.governance.registry.lab.trials("backdoor_confounding") == ()
    assert plane.governance.registry.lab.trials("covariate_shift") == ()
    assert len(
        plane.governance.registry.lab.trials(
            "interaction:backdoor_confounding+covariate_shift"
        )
    ) == 1


def test_semantic_plane_audit_rejects_unknown_evidence_and_duplicate_ids() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=32,
            max_per_family=5,
            minimum_rare_when_supported=2,
        )
    )
    observations = _observations()
    selection = plane.select(
        observations,
        requested=("backdoor_confounding",),
    )
    duplicate_a = SemanticFinding(
        finding_id="duplicate-id",
        lens_key="backdoor_confounding",
        family=LensFamily.CAUSAL,
        observation_ids=("plane-o1",),
        interpretation="First duplicate.",
        prediction="First duplicate prediction.",
        confidence=0.8,
        ambiguity=0.2,
        novelty=0.5,
        evidence_ids=("ev-1",),
    )
    duplicate_b = SemanticFinding(
        finding_id="duplicate-id",
        lens_key="backdoor_confounding",
        family=LensFamily.CAUSAL,
        observation_ids=("plane-o1",),
        interpretation="Second duplicate.",
        prediction="Second duplicate prediction.",
        confidence=0.8,
        ambiguity=0.2,
        novelty=0.5,
        evidence_ids=("ev-1",),
    )
    bad_evidence = SemanticFinding(
        finding_id="bad-evidence",
        lens_key="backdoor_confounding",
        family=LensFamily.CAUSAL,
        observation_ids=("plane-o1",),
        interpretation="Uses an evidence id absent from the observation.",
        prediction="Bad provenance should be rejected.",
        confidence=0.8,
        ambiguity=0.2,
        novelty=0.5,
        evidence_ids=("not-provenanced",),
    )

    audit = plane.audit_findings(
        (duplicate_a, duplicate_b, bad_evidence),
        observations=observations,
        selection=selection,
    )

    assert not audit.accepted
    assert audit.duplicate_finding_ids == ("duplicate-id",)
    assert audit.evidence_mismatch_ids == ("bad-evidence",)
    duplicate_reasons = [
        set(item.reasons)
        for item in audit.rejected
        if item.finding_id == "duplicate-id"
    ]
    assert len(duplicate_reasons) == 2
    assert all("duplicate_finding_id" in reasons for reasons in duplicate_reasons)
    bad = next(item for item in audit.rejected if item.finding_id == "bad-evidence")
    assert "evidence_not_provenanced_by_observations" in bad.reasons


def test_resolved_forecast_is_not_silently_reopened_and_revision_gets_new_identity() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=32,
            max_per_family=5,
            minimum_rare_when_supported=2,
        )
    )
    original = _finding(
        "lifecycle-concept-drift",
        "concept_drift",
        LensFamily.PREDICTIVE,
        confidence=0.80,
        ambiguity=0.20,
    )
    first = plane.analyze(
        _observations(),
        findings=(original,),
        requested=("concept_drift",),
    )
    first_forecast = next(
        item
        for item in first.forecasts
        if item.source_finding_ids == ("lifecycle-concept-drift",)
    )
    plane.resolve_forecast(
        first_forecast.forecast_id,
        outcome=True,
        domain="lifecycle",
        independent_run="lifecycle-001",
    )

    unchanged = plane.analyze(
        _observations(),
        findings=(original,),
        requested=("concept_drift",),
    )
    assert all(
        item.forecast_id != first_forecast.forecast_id
        for item in unchanged.forecasts
    )

    revised = _finding(
        "lifecycle-concept-drift",
        "concept_drift",
        LensFamily.PREDICTIVE,
        confidence=0.92,
        ambiguity=0.10,
    )
    second = plane.analyze(
        _observations(),
        findings=(revised,),
        requested=("concept_drift",),
    )
    second_forecast = next(
        item
        for item in second.forecasts
        if item.source_finding_ids == ("lifecycle-concept-drift",)
    )
    assert second_forecast.forecast_id != first_forecast.forecast_id


def test_interaction_calibration_conservatively_updates_future_fusion_reliability() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=36,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )
    findings = (
        _finding("cal-causal", "backdoor_confounding", LensFamily.CAUSAL),
        _finding("cal-shift", "covariate_shift", LensFamily.PREDICTIVE),
    )
    snapshot = plane.analyze(
        _observations(),
        findings=findings,
        requested=("backdoor_confounding", "covariate_shift"),
    )
    interaction_forecast = next(
        item
        for item in snapshot.forecasts
        if item.source_interaction_ids
        and set(item.source_lens_keys)
        == {"backdoor_confounding", "covariate_shift"}
    )
    before = plane._reliability_for_forecast(
        interaction_forecast,
        snapshot.governance,
    )
    plane.resolve_forecast(
        interaction_forecast.forecast_id,
        outcome=False,
        domain="calibration-loop",
        independent_run="calibration-loop-001",
    )
    after = plane._reliability_for_forecast(
        interaction_forecast,
        snapshot.governance,
    )

    assert 0.0 <= after <= before <= 1.0



def test_semantic_plane_persists_perpendicular_and_composition_tangents() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=40,
            max_per_family=6,
            minimum_rare_when_supported=2,
            max_perpendicular_axes=10,
            frontier_limit=8,
            frontier_max_per_axis=2,
            frontier_max_per_family=2,
        )
    )
    findings = (
        _finding("tangent-causal", "backdoor_confounding", LensFamily.CAUSAL),
        _finding("tangent-shift", "covariate_shift", LensFamily.PREDICTIVE),
    )
    snapshot = plane.analyze(
        _observations(),
        findings=findings,
        requested=("backdoor_confounding", "covariate_shift"),
        sequence=7,
    )
    assert snapshot.tangent_ids
    assert snapshot.coverage.tangent_count == len(set(snapshot.tangent_ids))
    assert snapshot.frontier.tangent_ids
    assert snapshot.coverage.frontier_tangent_count == len(snapshot.frontier.tangent_ids)
    assert len(snapshot.frontier.tangent_ids) <= 8
    assert any(
        node.created_sequence == 7
        for node in plane.tangent_graph.snapshot()
        if node.tangent_id in set(snapshot.tangent_ids)
    )


def test_shared_semantic_provenance_is_discounted_even_without_shared_observations() -> None:
    signals = (
        LensSignal(
            signal_id="signal-a",
            lens_key="backdoor_confounding",
            family=LensFamily.CAUSAL,
            probability=0.8,
            confidence=0.8,
            ambiguity=0.1,
            reliability=0.8,
            epistemic_strength=0.8,
            observation_ids=("obs-a",),
            evidence_ids=("ev-a",),
            calibration_group="group-a",
            provenance_ids=("finding-root",),
        ),
        LensSignal(
            signal_id="signal-b",
            lens_key="concept_drift",
            family=LensFamily.PREDICTIVE,
            probability=0.75,
            confidence=0.8,
            ambiguity=0.1,
            reliability=0.8,
            epistemic_strength=0.8,
            observation_ids=("obs-b",),
            evidence_ids=("ev-b",),
            calibration_group="group-b",
            provenance_ids=("finding-root",),
        ),
    )
    dependencies = LensFusionEngine().infer_dependencies(signals)
    assert any(
        edge.kind is LensDependenceKind.SHARED_PROVENANCE
        and edge.strength > 0.0
        for edge in dependencies
    )


def test_cross_family_interaction_forecast_uses_predictive_fusion_family() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=36,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )
    snapshot = plane.analyze(
        _observations(),
        findings=(
            _finding("family-causal", "backdoor_confounding", LensFamily.CAUSAL),
            _finding("family-shift", "covariate_shift", LensFamily.PREDICTIVE),
        ),
        requested=("backdoor_confounding", "covariate_shift"),
    )
    interaction = next(
        item
        for item in snapshot.fusion.contributions
        if item.lens_key == "backdoor_confounding+covariate_shift"
    )
    assert interaction.family is LensFamily.PREDICTIVE


def test_falsified_finding_cannot_emit_plane_forecast_or_interaction_forecast() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=36,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )
    falsified = SemanticFinding(
        finding_id="falsified-causal",
        lens_key="backdoor_confounding",
        family=LensFamily.CAUSAL,
        observation_ids=("plane-o1", "plane-o2"),
        interpretation="A falsified causal reading.",
        prediction="This forecast must not be emitted.",
        confidence=0.9,
        ambiguity=0.1,
        novelty=0.4,
        status=ReadingStatus.FALSIFIED,
        evidence_ids=("ev-1", "ev-2"),
    )
    shift = _finding("live-shift", "covariate_shift", LensFamily.PREDICTIVE)
    snapshot = plane.analyze(
        _observations(),
        findings=(falsified, shift),
        requested=("backdoor_confounding", "covariate_shift"),
    )
    assert all(
        "falsified-causal" not in forecast.source_finding_ids
        for forecast in snapshot.forecasts
    )
    blocked_interactions = {
        interaction.interaction_id
        for interaction in snapshot.composition.interactions
        if interaction.left_finding_id == "falsified-causal"
        or interaction.right_finding_id == "falsified-causal"
    }
    assert all(
        not (set(forecast.source_interaction_ids) & blocked_interactions)
        for forecast in snapshot.forecasts
    )
