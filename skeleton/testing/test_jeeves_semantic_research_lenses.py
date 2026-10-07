from __future__ import annotations

from skeleton.jeeves.agent.semantic_extreme_lenses import LensMaturity
from skeleton.jeeves.agent.semantic_lenses import LensFamily, SemanticObservation
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRegistry, MaximalLensRouter
from skeleton.jeeves.agent.semantic_research_lenses import (
    research_catalog_fingerprint,
    research_definitions_by_family,
    research_semantic_definitions,
    research_semantic_specs,
)


def _observations() -> tuple[SemanticObservation, ...]:
    return (
        SemanticObservation(
            "research-1",
            (
                "Telemetry shows queue backpressure and hidden state while public consensus "
                "differs from private reports."
            ),
            0,
            tags=("telemetry", "queue", "consensus"),
        ),
        SemanticObservation(
            "research-2",
            (
                "Late event-time records arrive out of order; an initial estimate anchors "
                "the next judgment while text and image repeat the same signal."
            ),
            1,
            tags=("event time", "anchor", "image"),
        ),
        SemanticObservation(
            "research-3",
            (
                "A diary retells the event, the aspect ratio changes, and one game action "
                "appears dominant across every modeled response."
            ),
            2,
            tags=("diary", "aspect ratio", "dominant"),
        ),
    )


def test_research_catalog_is_large_unique_and_scientifically_bounded() -> None:
    definitions = research_semantic_definitions()
    specs = research_semantic_specs()
    keys = [definition.spec.key for definition in definitions]

    assert len(definitions) == 48
    assert len(specs) == len(definitions)
    assert len(keys) == len(set(keys))
    assert all(definition.spec.rare for definition in definitions)
    assert all(definition.lineage for definition in definitions)
    assert all(definition.transfer_warning for definition in definitions)
    assert all(isinstance(definition.maturity, LensMaturity) for definition in definitions)

    grouped = research_definitions_by_family(definitions)
    assert len(grouped[LensFamily.SYSTEM]) >= 6
    assert len(grouped[LensFamily.SOCIAL]) >= 6
    assert len(grouped[LensFamily.TEMPORAL]) >= 6
    assert len(grouped[LensFamily.COGNITIVE]) >= 6
    assert len(grouped[LensFamily.RHETORIC]) >= 6
    assert len(grouped[LensFamily.SEMIOTIC]) >= 5
    assert len(grouped[LensFamily.NARRATIVE]) >= 3
    assert len(grouped[LensFamily.FILM]) >= 4
    assert len(grouped[LensFamily.GAME]) >= 4


def test_research_catalog_integrates_into_maximal_registry_without_collisions() -> None:
    registry = MaximalSemanticRegistry()
    registry_keys = {spec.key for spec in registry.all()}
    research_keys = {spec.key for spec in research_semantic_specs()}

    assert research_keys.issubset(registry_keys)
    assert len(registry_keys) == len(registry.all())
    assert {
        "observability_gap",
        "queue_backpressure",
        "pluralistic_ignorance",
        "event_time_processing_time",
        "memory_confidence_dissociation",
        "equivocation_drift",
        "multimodal_redundancy",
        "epistolary_mediation",
        "aspect_ratio_reframing",
        "dominant_strategy_pressure",
    }.issubset(registry_keys)


def test_maximal_router_can_route_research_lenses_across_perpendicular_families() -> None:
    router = MaximalLensRouter()
    requested = (
        "observability_gap",
        "pluralistic_ignorance",
        "event_time_processing_time",
        "anchoring_adjustment",
        "equivocation_drift",
        "multimodal_redundancy",
        "epistolary_mediation",
        "aspect_ratio_reframing",
        "dominant_strategy_pressure",
    )

    selection = router.select_maximal(
        _observations(),
        requested=requested,
        max_lenses=36,
        max_per_family=5,
        minimum_rare_when_supported=3,
    )

    selected = {spec.key for spec in selection.lenses}
    assert set(requested).issubset(selected)
    assert {
        LensFamily.SYSTEM,
        LensFamily.SOCIAL,
        LensFamily.TEMPORAL,
        LensFamily.COGNITIVE,
        LensFamily.RHETORIC,
        LensFamily.SEMIOTIC,
        LensFamily.LITERATURE,
        LensFamily.FILM,
        LensFamily.GAME,
    }.issubset(set(selection.families))


def test_research_catalog_fingerprint_is_stable_and_content_addressed() -> None:
    first = research_catalog_fingerprint()
    second = research_catalog_fingerprint()

    assert first == second
    assert len(first) == 64
