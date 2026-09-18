from __future__ import annotations

from skeleton.jeeves.agent.lens_governance import (
    LensPermission,
    ScientificGrade,
)
from skeleton.jeeves.agent.lens_hypergraph import SemanticLensHypergraph
from skeleton.jeeves.agent.semantic_governance_bridge import SemanticGovernanceBridge
from skeleton.jeeves.agent.semantic_lenses import (
    LensFamily,
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
