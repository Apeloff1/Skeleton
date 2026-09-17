from __future__ import annotations

from skeleton.jeeves.agent.context_pipeline import LayeredContextResolver, ResolutionPolicy
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex
from skeleton.jeeves.agent.nuance_runtime import ScientificNuanceRuntime
from skeleton.jeeves.agent.perpendicular_semantics import PerpendicularExpansionPlanner
from skeleton.jeeves.agent.relational_memory import RelationalMemoryIndex
from skeleton.jeeves.agent.semantic_deep_lenses import deep_lens_lineage, deep_semantic_lenses
from skeleton.jeeves.agent.semantic_frontier import FrontierSemanticRegistry
from skeleton.jeeves.agent.semantic_lenses import LensFamily, SemanticFinding, SemanticObservation


def _runtime():
    namespace = MemoryNamespace("tenant", "user", session_id="session")
    cards = MemoryGameIndex()
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
    return namespace, relations, ScientificNuanceRuntime(resolver)


def test_deep_catalog_registers_without_colliding_with_existing_lenses():
    registry = FrontierSemanticRegistry()
    deep = deep_semantic_lenses()
    keys = [item.key for item in deep]
    assert len(deep) >= 60
    assert len(keys) == len(set(keys))
    for key in keys:
        assert registry.get(key).key == key


def test_deep_lineage_keeps_scientific_boundary_metadata():
    lineage = deep_lens_lineage()
    assert "match_cut_semantic_bridge" in lineage
    assert "scalar_implicature_strength" in lineage
    assert "dialogue_optionality_pragmatic_act" in lineage
    assert all(item.boundary.strip() for item in lineage.values())


def test_semantic_observation_has_stable_content_sensitive_fingerprint():
    left = SemanticObservation("obs", "match cut from eye to moon", 0, tags=("film",))
    same = SemanticObservation("obs", "match cut from eye to moon", 0, tags=("film",))
    changed = SemanticObservation("obs", "jump cut across time", 0, tags=("film",))
    assert left.fingerprint == same.fingerprint
    assert left.fingerprint != changed.fingerprint


def test_perpendicular_planner_never_forces_zero_cue_rare_lenses():
    registry = FrontierSemanticRegistry()
    planner = PerpendicularExpansionPlanner(registry)
    observations = (
        SemanticObservation("obs:1", "A plain database transaction commits successfully.", 0),
    )
    plan = planner.plan(observations)
    assert all(candidate.support > 0.0 for candidate in plan.candidates)
    assert all(candidate.trigger_terms for candidate in plan.candidates)


def test_perpendicular_planner_finds_cross_family_supported_axes():
    registry = FrontierSemanticRegistry()
    planner = PerpendicularExpansionPlanner(registry)
    observations = (
        SemanticObservation(
            "obs:1",
            "A match cut juxtaposes two scenes while the player chooses a dialogue option and a narrator withholds information.",
            0,
            tags=("film", "game", "narrative"),
        ),
        SemanticObservation(
            "obs:2",
            "The abrupt cut changes interpretation; the game choice acts like a promise and the story leaves a gap.",
            1,
            tags=("contrast", "dialogue"),
        ),
    )
    plan = planner.plan(observations, maximum_axes=10)
    families = {candidate.family.value for candidate in plan.candidates}
    assert "film" in families
    assert len(families) >= 2
    assert all(candidate.prediction.strip() for candidate in plan.candidates)
    assert all(candidate.failure_mode.strip() for candidate in plan.candidates)


def test_nuance_runtime_learns_turn_relations_prequentially():
    namespace, _, runtime = _runtime()
    first = runtime.prepare(namespace, "alpha state")
    second = runtime.prepare(namespace, "beta state")
    third = runtime.prepare(namespace, "alpha state")
    fourth = runtime.prepare(namespace, "beta state")

    assert first.relation_sequence is not None
    assert not first.relation_sequence.transition_predictions
    assert second.relation_sequence is not None
    assert third.relation_sequence is not None
    assert fourth.relation_sequence is not None
    assert fourth.relation_sequence.transition_predictions

    predicted = {
        item.target_card_id: item.probability
        for item in fourth.relation_sequence.transition_predictions
    }
    assert fourth.captured_card_id in predicted
    assert predicted[fourth.captured_card_id] > 0.0


def test_prepare_resolves_before_capture_so_current_turn_cannot_self_hit():
    namespace, _, runtime = _runtime()
    frame = runtime.prepare(namespace, "unique first-turn token zephyrcard")
    assert frame.captured_card_id is not None
    assert not any(
        item.item_id == frame.captured_card_id
        for item in frame.context.items
    )


def test_checkpoint_runs_perpendicular_audit_without_registered_findings():
    namespace, _, runtime = _runtime()
    frame = runtime.prepare(
        namespace,
        "A match cut juxtaposes a face and an object; a dialogue choice withholds information from the player.",
    )
    packet = runtime.checkpoint_before_restart(frame.frame_id, sequence=1)
    assert packet.packet_fingerprint
    # The graph checkpoint must be valid even when the active semantic model
    # has not yet returned findings.
    assert packet.graph_bundle.root_fingerprint == frame.fingerprint


def test_validated_pairwise_finding_enters_relational_hypothesis_memory():
    namespace, relations, runtime = _runtime()
    first = runtime.prepare(namespace, "neutral face observation")
    frame = runtime.prepare(
        namespace,
        "neutral face beside a coffin image creates montage contrast and juxtaposition",
        requested_lenses=("montage_collision",),
    )
    prior_observation = next(
        item
        for item in frame.observations
        if item.metadata.get("context_item_id") == first.captured_card_id
    )
    current_observation = frame.observations[0]
    finding = SemanticFinding(
        finding_id="finding:montage",
        lens_key="montage_collision",
        family=LensFamily.FILM,
        observation_ids=(prior_observation.observation_id, current_observation.observation_id),
        interpretation="The paired observations support a contrast reading.",
        prediction="Changing the neighboring image should change the induced reading.",
        confidence=0.82,
        ambiguity=0.35,
        novelty=0.72,
    )
    update = runtime.register_findings(frame, (finding,), sequence=1)
    assert update.relational_hypothesis_ids
    trace = relations.store.get(update.relational_hypothesis_ids[0])
    assert trace is not None
    assert trace.metadata["semantic_hypothesis"] is True
    assert trace.metadata["finding_id"] == finding.finding_id
    assert trace.kind.value == "contrast"
