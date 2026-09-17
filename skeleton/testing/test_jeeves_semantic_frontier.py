from __future__ import annotations

from skeleton.jeeves.agent.semantic_frontier import (
    FrontierLensRouter,
    FrontierSemanticRegistry,
    LensCompositionEngine,
    LensInteractionKind,
)
from skeleton.jeeves.agent.semantic_lenses import LensFamily, ReadingStatus, SemanticFinding, SemanticObservation
from skeleton.jeeves.agent.semantic_prediction import PredictionStatus, SemanticPredictionLedger, SemanticPredictiveModel
from skeleton.jeeves.agent.semantic_tangent_bridge import SemanticTangentBridge


def _finding(
    finding_id: str,
    lens_key: str,
    family: LensFamily,
    *,
    confidence: float = 0.8,
    ambiguity: float = 0.5,
    novelty: float = 0.7,
    counterreading: str = "",
    prediction: str = "The next relevant observation will discriminate this reading.",
) -> SemanticFinding:
    return SemanticFinding(
        finding_id=finding_id,
        lens_key=lens_key,
        family=family,
        observation_ids=("obs-a", "obs-b"),
        interpretation=f"Interpretation under {lens_key}",
        prediction=prediction,
        confidence=confidence,
        ambiguity=ambiguity,
        novelty=novelty,
        status=ReadingStatus.CONTESTED if counterreading else ReadingStatus.CANDIDATE,
        evidence_ids=("ev-1",),
        counterreading=counterreading,
    )


def test_frontier_registry_contains_rare_film_literary_and_game_lenses() -> None:
    registry = FrontierSemanticRegistry()
    keys = {spec.key for spec in registry.all()}
    required = {
        "intellectual_montage",
        "overtonal_montage",
        "vertical_metalepsis",
        "fabula_syuzhet",
        "heteroglossia",
        "procedural_rhetoric",
        "player_enactment_counterlens",
        "possibility_space",
        "information_set",
        "signaling_game",
        "sequence_break",
        "false_affordance",
    }
    assert required <= keys
    families = {spec.family for spec in registry.all() if spec.key in required}
    assert LensFamily.FILM in families
    assert LensFamily.LITERATURE in families or LensFamily.NARRATIVE in families
    assert LensFamily.GAME in families
    assert sum(spec.rare for spec in registry.all()) >= 20


def test_frontier_router_prefers_perpendicular_families_and_supported_rare_lenses() -> None:
    observations = (
        SemanticObservation("o1", "A montage cut juxtaposition creates an abstract metaphor", 0, tags=("film", "contrast")),
        SemanticObservation("o2", "The narrator enters the story and breaks the narrative level", 1, tags=("narrative",)),
        SemanticObservation("o3", "Players break intended rules through sequence break and creative play", 2, tags=("game", "player")),
    )
    selection = FrontierLensRouter().select_frontier(observations, max_lenses=12, minimum_rare_when_supported=2)
    assert len(selection.families) >= 3
    assert any(spec.rare for spec in selection.lenses)
    assert selection.perpendicular is True


def test_procedural_rules_and_enacted_play_remain_a_conflict_not_an_average() -> None:
    formal = _finding("formal", "procedural_rhetoric", LensFamily.GAME, confidence=0.86, ambiguity=0.35)
    enacted = _finding(
        "enacted",
        "player_enactment_counterlens",
        LensFamily.GAME,
        confidence=0.79,
        ambiguity=0.45,
        counterreading="Players appropriate the rule system in a different direction.",
    )
    composition = LensCompositionEngine().compose((formal, enacted))
    assert len(composition.interactions) == 1
    interaction = composition.interactions[0]
    assert interaction.rule.kind is LensInteractionKind.CONFLICTS
    assert interaction.interaction_id in composition.unresolved_conflicts
    assert interaction.metadata["interpretive_only"] is True
    assert interaction.metadata["may_promote_to_evidence"] is False
    assert composition.tangent_seeds


def test_semantic_predictions_are_provisional_and_scored_only_after_outcome() -> None:
    finding = _finding(
        "film-reading",
        "intellectual_montage",
        LensFamily.FILM,
        confidence=0.9,
        ambiguity=0.4,
        prediction="A repeated A/B juxtaposition will elicit the same abstract association.",
    )
    model = SemanticPredictiveModel(clock=lambda: 10.0)
    forecast = model.from_finding(finding)
    assert forecast is not None
    assert 0.5 < forecast.probability < 0.9
    assert forecast.status is PredictionStatus.OPEN
    assert forecast.metadata["is_evidence"] is False

    ledger = SemanticPredictionLedger(clock=lambda: 20.0)
    ledger.add(forecast)
    resolved = ledger.resolve(forecast.forecast_id, outcome=True, observation_id="future-obs")
    assert resolved.status is PredictionStatus.RESOLVED
    report = ledger.evaluate()
    assert report.count == 1
    assert 0.0 <= report.brier <= 1.0
    assert report.log_score >= 0.0


def test_ambiguity_shrinks_semantic_forecast_toward_half() -> None:
    model = SemanticPredictiveModel(clock=lambda: 1.0)
    low_ambiguity = model.from_finding(_finding("low", "motif_recurrence", LensFamily.LITERATURE, confidence=0.9, ambiguity=0.05))
    high_ambiguity = model.from_finding(_finding("high", "motif_recurrence", LensFamily.LITERATURE, confidence=0.9, ambiguity=0.95))
    assert low_ambiguity is not None and high_ambiguity is not None
    assert abs(high_ambiguity.probability - 0.5) < abs(low_ambiguity.probability - 0.5)


def test_restart_packet_preserves_semantic_conflicts_under_same_root() -> None:
    formal = _finding("formal", "procedural_rhetoric", LensFamily.GAME, confidence=0.84, ambiguity=0.55)
    enacted = _finding(
        "enacted",
        "player_enactment_counterlens",
        LensFamily.GAME,
        confidence=0.81,
        ambiguity=0.62,
        counterreading="Observed play departs from the formal procedure.",
    )
    composition = LensCompositionEngine().compose((formal, enacted))
    bridge = SemanticTangentBridge()
    root = "run-root-fingerprint"
    nodes = bridge.ingest((formal, enacted), composition=composition, root_fingerprint=root, sequence=7)
    assert nodes
    assert all(node.root_fingerprint == root for node in nodes)

    packet = bridge.restart_packet(
        root_fingerprint=root,
        sequence=8,
        findings=(formal, enacted),
        composition=composition,
        prediction_ids=("pred-1",),
    )
    assert packet.unresolved_conflict_ids == composition.unresolved_conflicts
    assert packet.graph_bundle.open_ids or packet.graph_bundle.active_ids
    assert set(packet.frontier.tangent_ids) & {node.tangent_id for node in nodes}
    assert packet.prediction_ids == ("pred-1",)



def test_frontier_registry_contains_new_temporal_auditory_and_ludic_level_lenses() -> None:
    registry = FrontierSemanticRegistry()
    keys = {spec.key for spec in registry.all()}
    required = {
        "point_of_audition",
        "embodied_sound_perspective",
        "narrative_frequency",
        "discourse_duration_ratio",
        "ludic_diegetic_interaction_levels",
        "affordance_feedback_triad",
        "dialogue_option_execution_gap",
        "substrate_simulation_experience_stack",
    }
    assert required <= keys
    assert all(registry.get(key).rare for key in required)


def test_narrative_frequency_separates_repeated_telling_from_repeated_event() -> None:
    frequency = _finding(
        "frequency",
        "narrative_frequency",
        LensFamily.NARRATIVE,
        confidence=0.88,
        ambiguity=0.30,
        prediction="Repeated event-level occurrence should predict future recurrence better than retelling alone.",
    )
    motif = _finding(
        "motif",
        "motif_recurrence",
        LensFamily.LITERATURE,
        confidence=0.82,
        ambiguity=0.35,
        prediction="The motif will recur.",
    )
    composition = LensCompositionEngine().compose((frequency, motif))
    assert len(composition.interactions) == 1
    interaction = composition.interactions[0]
    assert interaction.rule.kind is LensInteractionKind.CONDITIONS
    assert "event" in interaction.rule.question.casefold()
    assert interaction.metadata["may_promote_to_evidence"] is False


def test_dialogue_ludic_diegetic_gap_and_affordance_triad_form_distinct_lenses() -> None:
    observations = (
        SemanticObservation(
            "o1",
            "The dialogue option paraphrase promises refusal, but the character says yes.",
            0,
            tags=("game", "dialogue option", "player"),
        ),
        SemanticObservation(
            "o2",
            "The button looks usable and highlights, but feedback says the door cannot interact.",
            1,
            tags=("interface", "affordance", "feedback"),
        ),
    )
    selection = FrontierLensRouter().select_frontier(
        observations,
        requested=(
            "ludic_diegetic_interaction_levels",
            "dialogue_option_execution_gap",
            "affordance_feedback_triad",
        ),
        max_lenses=12,
        minimum_rare_when_supported=2,
    )
    selected = {spec.key for spec in selection.lenses}
    assert {
        "ludic_diegetic_interaction_levels",
        "dialogue_option_execution_gap",
        "affordance_feedback_triad",
    } <= selected

    level = _finding(
        "level",
        "ludic_diegetic_interaction_levels",
        LensFamily.GAME,
        confidence=0.9,
        ambiguity=0.25,
    )
    gap = _finding(
        "gap",
        "dialogue_option_execution_gap",
        LensFamily.GAME,
        confidence=0.87,
        ambiguity=0.32,
    )
    composition = LensCompositionEngine().compose((level, gap))
    assert len(composition.interactions) == 1
    assert composition.interactions[0].rule.kind is LensInteractionKind.REINFORCES


def test_point_of_audition_and_subjective_camera_preserve_multimodal_viewpoint_uncertainty() -> None:
    auditory = _finding(
        "auditory",
        "point_of_audition",
        LensFamily.FILM,
        confidence=0.84,
        ambiguity=0.38,
    )
    visual = _finding(
        "visual",
        "subjective_camera",
        LensFamily.FILM,
        confidence=0.80,
        ambiguity=0.41,
    )
    composition = LensCompositionEngine().compose((auditory, visual))
    assert len(composition.interactions) == 1
    interaction = composition.interactions[0]
    assert interaction.rule.kind is LensInteractionKind.REINFORCES
    assert "world" in interaction.rule.rationale.casefold()
    assert interaction.evidence_ids == ("ev-1",)
