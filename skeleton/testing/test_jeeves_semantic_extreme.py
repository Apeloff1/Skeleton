from __future__ import annotations

from skeleton.jeeves.agent.semantic_extreme_lenses import (
    LensMaturity,
    definitions_by_family,
    rare_semantic_definitions,
)
from skeleton.jeeves.agent.semantic_lenses import LensFamily, SemanticObservation
from skeleton.jeeves.agent.semantic_maximal import MaximalLensRouter, MaximalSemanticRegistry


def test_rare_catalog_is_large_unique_and_scientifically_annotated() -> None:
    definitions = rare_semantic_definitions()
    assert len(definitions) >= 50
    keys = [definition.spec.key for definition in definitions]
    assert len(keys) == len(set(keys))
    for definition in definitions:
        assert definition.lineage
        assert isinstance(definition.maturity, LensMaturity)
        assert definition.transfer_warning.strip()
        assert definition.spec.predicts.strip()
        assert definition.spec.failure_mode.strip()
        assert definition.spec.rare is True


def test_rare_catalog_spans_film_literature_games_and_memory_science() -> None:
    grouped = definitions_by_family()
    assert LensFamily.FILM in grouped
    assert LensFamily.LITERATURE in grouped
    assert LensFamily.GAME in grouped
    assert LensFamily.COGNITIVE in grouped
    assert len(grouped[LensFamily.FILM]) >= 10
    assert len(grouped[LensFamily.GAME]) >= 10
    cognitive_keys = {item.spec.key for item in grouped[LensFamily.COGNITIVE]}
    assert {"source_monitoring", "encoding_specificity", "retrieval_induced_forgetting"} <= cognitive_keys


def test_maximal_registry_merges_frontier_and_rare_catalog_without_duplicate_keys() -> None:
    registry = MaximalSemanticRegistry()
    keys = [spec.key for spec in registry.all()]
    assert len(keys) == len(set(keys))
    assert "intellectual_montage" in keys
    assert "rashomon_variance" in keys
    assert "source_monitoring" in keys
    assert "deckbuilding_interaction_graph" in keys
    assert "scope_ambiguity" in keys


def test_maximal_router_keeps_perpendicular_family_diversity() -> None:
    observations = (
        SemanticObservation("film", "A graphic match and cut juxtapose two visual shapes.", 0, tags=("film",)),
        SemanticObservation("text", "Some readers infer a stronger unstated alternative.", 1, tags=("language",)),
        SemanticObservation("game", "A hidden role player bluffs while a cooldown opens a response window.", 2, tags=("game",)),
        SemanticObservation("memory", "The user recalls the content but is unsure where it came from.", 3, tags=("memory",)),
    )
    selection = MaximalLensRouter().select_maximal(observations, max_lenses=20)
    assert selection.perpendicular is True
    assert len(selection.families) >= 4
    selected = {spec.key for spec in selection.lenses}
    assert selected & {"graphic_match", "shot_reverse_shot_suture"}
    assert selected & {"scalar_implicature", "scope_ambiguity"}
    assert selected & {"hidden_role_belief", "cooldown_window"}
    assert "source_monitoring" in selected
