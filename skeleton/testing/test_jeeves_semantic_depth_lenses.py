from __future__ import annotations

from skeleton.jeeves.agent.lens_governance import ScientificGrade
from skeleton.jeeves.agent.semantic_depth_interactions import (
    depth_interaction_keys,
    depth_interaction_rules,
)
from skeleton.jeeves.agent.semantic_depth_lenses import (
    depth_catalog_fingerprint,
    depth_definitions_by_family,
    depth_semantic_definitions,
    depth_semantic_specs,
)
from skeleton.jeeves.agent.semantic_governance_bridge import SemanticGovernanceBridge
from skeleton.jeeves.agent.semantic_lenses import (
    LensFamily,
    SemanticFinding,
    SemanticObservation,
)
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry
from skeleton.jeeves.agent.semantic_lens_topology import SemanticLensTopology
from skeleton.jeeves.agent.semantic_plane import SemanticLensPlane, SemanticPlanePolicy
from skeleton.jeeves.agent.semantic_plane_interactions import plane_interaction_keys


def _observations() -> tuple[SemanticObservation, ...]:
    return (
        SemanticObservation(
            "depth-o1",
            (
                "A retry storm increases queue backpressure while a circuit breaker "
                "changes service state. A leading indicator has a stable lag but "
                "calibration drifts after concept drift."
            ),
            0,
            evidence_ids=("depth-ev-1",),
            tags=("retry", "queue", "leading", "calibration"),
        ),
        SemanticObservation(
            "depth-o2",
            (
                "A network diffusion pattern may include interference spillover. "
                "The same summary is lossy under a token budget and active query "
                "value depends on remaining uncertainty."
            ),
            1,
            evidence_ids=("depth-ev-2",),
            tags=("network", "spillover", "summary", "query"),
        ),
        SemanticObservation(
            "depth-o3",
            (
                "Residual autocorrelation grows with forecast horizon while target "
                "leakage and temporal validation leakage remain possible."
            ),
            2,
            evidence_ids=("depth-ev-3",),
            tags=("residual", "horizon", "leakage", "validation"),
        ),
    )


def _finding(
    finding_id: str,
    lens_key: str,
    family: LensFamily,
    *,
    observation_ids: tuple[str, ...] = ("depth-o1", "depth-o2"),
    evidence_ids: tuple[str, ...] = ("depth-ev-1", "depth-ev-2"),
) -> SemanticFinding:
    return SemanticFinding(
        finding_id=finding_id,
        lens_key=lens_key,
        family=family,
        observation_ids=observation_ids,
        interpretation=f"{lens_key} is a depth reading.",
        prediction=f"A future observation should discriminate {lens_key}.",
        confidence=0.78,
        ambiguity=0.22,
        novelty=0.72,
        evidence_ids=evidence_ids,
    )


def test_depth_catalog_is_balanced_across_every_semantic_family() -> None:
    definitions = depth_semantic_definitions()
    specs = depth_semantic_specs()
    grouped = depth_definitions_by_family(definitions)
    keys = [item.spec.key for item in definitions]

    assert len(definitions) == 48
    assert len(specs) == 48
    assert len(keys) == len(set(keys))
    assert set(grouped) == set(LensFamily)
    assert all(len(grouped[family]) == 3 for family in LensFamily)
    assert all(item.spec.rare for item in definitions)
    assert all(item.lineage for item in definitions)
    assert all(item.transfer_warning for item in definitions)
    assert len(depth_catalog_fingerprint()) == 64


def test_depth_catalog_integrates_without_registry_collisions() -> None:
    registry = MaximalSemanticRegistry()
    keys = [spec.key for spec in registry.all()]
    depth_keys = {spec.key for spec in depth_semantic_specs()}

    assert len(keys) == len(set(keys))
    assert depth_keys.issubset(set(keys))
    assert {
        "continuity_space_graph",
        "narrative_distance",
        "counterplay_window",
        "causal_story_gap",
        "multimodal_conflict",
        "working_memory_load",
        "presupposition_failure",
        "common_knowledge_gap",
        "lag_structure",
        "retry_storm",
        "frontdoor_identification",
        "active_query_value",
        "scheduler_fairness",
        "search_diversity_audit",
        "exchangeability_break",
        "target_leakage",
    }.issubset(set(keys))


def test_depth_interactions_are_unique_and_do_not_shadow_plane_rules() -> None:
    rules = depth_interaction_rules()
    keys = depth_interaction_keys()
    plane = set(plane_interaction_keys())

    assert len(rules) == 46
    assert len(keys) == 46
    assert len(keys) == len(set(keys))
    assert not (set(keys) & plane)


def test_depth_router_can_span_all_sixteen_families_in_one_selection() -> None:
    requested = (
        "continuity_space_graph",
        "narrative_distance",
        "counterplay_window",
        "causal_story_gap",
        "multimodal_conflict",
        "working_memory_load",
        "presupposition_failure",
        "common_knowledge_gap",
        "lag_structure",
        "retry_storm",
        "frontdoor_identification",
        "active_query_value",
        "scheduler_fairness",
        "search_diversity_audit",
        "exchangeability_break",
        "target_leakage",
    )
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=48,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )

    selection = plane.select(_observations(), requested=requested)

    selected = {spec.key for spec in selection.lenses}
    assert set(requested).issubset(selected)
    assert set(selection.families) == set(LensFamily)


def test_depth_maturity_is_visible_to_scientific_governance() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=24,
            max_per_family=5,
            minimum_rare_when_supported=2,
        )
    )
    selection = plane.select(
        _observations(),
        requested=("frontdoor_identification", "search_diversity_audit"),
    )
    governance = SemanticGovernanceBridge().assess(
        selection,
        observations=_observations(),
    )

    formal = governance.decision_for("frontdoor_identification")
    heuristic = governance.decision_for("search_diversity_audit")
    assert formal is not None
    assert heuristic is not None
    assert formal.grade is ScientificGrade.FORMAL
    assert heuristic.grade is ScientificGrade.HEURISTIC
    assert formal.factual_assertion_authorized is False
    assert formal.causal_assertion_authorized is False
    assert heuristic.factual_assertion_authorized is False
    assert heuristic.causal_assertion_authorized is False


def test_depth_interaction_executes_inside_full_semantic_plane() -> None:
    plane = SemanticLensPlane(
        policy=SemanticPlanePolicy(
            max_lenses=32,
            max_per_family=6,
            minimum_rare_when_supported=2,
        )
    )
    observations = _observations()
    snapshot = plane.analyze(
        observations,
        findings=(
            _finding(
                "retry-depth",
                "retry_storm",
                LensFamily.SYSTEM,
                observation_ids=("depth-o1",),
                evidence_ids=("depth-ev-1",),
            ),
            _finding(
                "queue-first-order",
                "queue_backpressure",
                LensFamily.SYSTEM,
                observation_ids=("depth-o1",),
                evidence_ids=("depth-ev-1",),
            ),
        ),
        requested=("retry_storm", "queue_backpressure"),
    )

    interaction = next(
        item
        for item in snapshot.composition.interactions
        if set(item.rule.key) == {"retry_storm", "queue_backpressure"}
    )
    assert interaction.rule.predictive_effect
    assert interaction.observation_ids == ("depth-o1",)
    assert interaction.metadata["interpretive_only"] is True
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False


def test_semantic_plane_contract_fingerprint_includes_depth_registry_and_rules() -> None:
    plane = SemanticLensPlane()
    fingerprint = plane.fingerprint

    assert len(fingerprint) == 64
    assert plane.registry.get("target_leakage").family is LensFamily.PREDICTIVE
    rule = plane.composition.rule_for("retry_storm", "queue_backpressure")
    assert rule is not None
    assert set(rule.key) == {"retry_storm", "queue_backpressure"}



def test_semantic_topology_covers_registered_rules_without_dangling_edges() -> None:
    registry = MaximalSemanticRegistry()
    topology = SemanticLensTopology(registry)
    snapshot = topology.snapshot
    registered = {spec.key for spec in registry.all()}

    assert len(snapshot.nodes) == len(registered)
    assert len(snapshot.edges) >= 76
    assert all(edge.left_key in registered for edge in snapshot.edges)
    assert all(edge.right_key in registered for edge in snapshot.edges)
    assert len({edge.edge_id for edge in snapshot.edges}) == len(snapshot.edges)
    assert snapshot.component_count >= 1
    assert snapshot.largest_component_size >= 2
    assert snapshot.conflict_edge_ids
    assert snapshot.reinforcement_edge_ids


def test_semantic_topology_connects_depth_rules_across_rule_layers() -> None:
    topology = SemanticLensTopology(MaximalSemanticRegistry())

    assert "queue_backpressure" in topology.neighbors("retry_storm")
    path = topology.shortest_path(
        "retry_storm",
        "forecast_horizon_decay",
        max_depth=4,
    )

    assert path
    assert path[0] == "retry_storm"
    assert path[-1] == "forecast_horizon_decay"
    assert "queue_backpressure" in path


def test_semantic_topology_bridge_candidates_are_bounded_and_not_existing_edges() -> None:
    topology = SemanticLensTopology(MaximalSemanticRegistry())
    candidates = topology.bridge_candidates(limit=20, minimum_score=0.18)

    assert len(candidates) <= 20
    assert candidates
    for candidate in candidates:
        assert candidate.shared_cues
        assert candidate.score >= 0.18
        assert candidate.right_key not in topology.neighbors(candidate.left_key)
        assert 0.0 <= candidate.cue_overlap <= 1.0
        assert 0.0 <= candidate.role_novelty <= 1.0


def test_semantic_plane_snapshot_exposes_static_topology_diagnostics() -> None:
    plane = SemanticLensPlane()
    snapshot = plane.analyze(
        _observations(),
        requested=("retry_storm", "target_leakage"),
    )

    assert snapshot.topology.fingerprint == plane.topology.fingerprint
    assert snapshot.coverage.topology_components == snapshot.topology.component_count
    assert (
        snapshot.coverage.topology_isolated_lenses
        == len(snapshot.topology.isolated_lens_keys)
    )
    assert (
        snapshot.coverage.topology_bridge_lenses
        == len(snapshot.topology.bridge_lens_keys)
    )
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False
