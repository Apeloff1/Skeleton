from __future__ import annotations

import json

import pytest

from skeleton.jeeves.agent.relational_memory import RelationalMemoryIndex
from skeleton.jeeves.agent.context_pipeline import LayeredContextResolver, ResolutionPolicy
from skeleton.jeeves.agent.evidence import EvidenceLedger
from skeleton.jeeves.agent.interpretive_science import ScientificLensLab
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.nuance_runtime import (
    NuanceRuntimeError,
    ScientificContextCompiler,
)
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.scientific_runtime import ScientificJeevesRuntime
from skeleton.jeeves.agent.semantic_lenses import (
    LensFamily,
    SemanticFinding,
    SemanticObservation,
)
from skeleton.jeeves.agent.semantic_plane import SemanticLensPlane
from skeleton.jeeves.agent.types import (
    AgentResult,
    Goal,
    TerminationReason,
    Usage,
)


class TickClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def _namespace() -> MemoryNamespace:
    return MemoryNamespace("tenant", "user", "workspace", "session")


def _goal() -> Goal:
    return Goal(
        "goal-1",
        (
            "Compare a montage juxtaposition with a player sequence break and "
            "estimate the probability of the next remembered cue."
        ),
        metadata={"domain": "narrative-game-analysis"},
    )


def _compiler(clock: TickClock):
    memory = MemoryManager(clock=clock)
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0), clock=clock)
    relations = RelationalMemoryIndex(cards, clock=clock)
    resolver = LayeredContextResolver(
        cards=cards,
        memory=memory,
        relations=relations,
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            maximum_tier=1,
        ),
    )
    semantic_plane = SemanticLensPlane()
    return (
        memory,
        cards,
        relations,
        resolver,
        ScientificContextCompiler(
            resolver,
            semantic_plane=semantic_plane,
        ),
    )


def test_scientific_context_compiler_preserves_base_packet_contract_and_adds_workbench() -> None:
    clock = TickClock()
    memory, cards, _, _, compiler = _compiler(clock)
    namespace = _namespace()
    prior = cards.capture_interaction(
        namespace,
        "Earlier the player ignored a warning after a match cut.",
        context_tags=("film", "game"),
        trust=0.85,
        salience=0.80,
    )

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Plan a bounded analysis.",
        goal=_goal(),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
    )

    assert packet.messages()
    assert "scientific_nuance_workbench" in packet.retained_sections
    assert "context_index_card" in packet.retained_sections
    workbench = next(
        section for section in packet.sections if section.name == "scientific_nuance_workbench"
    )
    payload = json.loads(workbench.content)
    assert payload["contract"]["interpretive_only"] is True
    assert payload["contract"]["semantic_readings_are_not_evidence"] is True
    assert payload["contract"]["relations_change_retrieval_priority_not_factual_trust"] is True
    assert payload["contract"]["governed_semantic_plane"] is True
    assert payload["contract"]["semantic_lens_weights_are_domain_scoped"] is True
    assert payload["semantic_domain"] == "narrative-game-analysis"
    assert payload["semantic_governance_fingerprint"]
    assert any(row["family"] == "film" for row in payload["lenses"])
    assert payload["governed_semantic_lenses"]
    assert all(
        row["factual_assertion_authorized"] is False
        for row in payload["governed_semantic_lenses"]
    )
    assert all(
        row["causal_assertion_authorized"] is False
        for row in payload["governed_semantic_lenses"]
    )
    assert prior.card_id in {
        source_id
        for section in packet.sections
        if section.name == "context_index_card"
        for source_id in section.source_ids
    }


def test_scientific_context_compiler_rejects_split_memory_planes() -> None:
    clock = TickClock()
    memory, _, _, _, compiler = _compiler(clock)

    with pytest.raises(NuanceRuntimeError, match="share the runtime MemoryManager"):
        compiler.compile(
            system_instruction="system",
            task_instruction="task",
            goal=_goal(),
            namespace=_namespace(),
            memory=MemoryManager(clock=clock),
            evidence=EvidenceLedger(clock=clock),
        )

    # Sanity: the intended shared memory plane remains accepted.
    packet = compiler.compile(
        system_instruction="system",
        task_instruction="task",
        goal=_goal(),
        namespace=_namespace(),
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
    )
    assert packet.fingerprint


def test_scientific_runtime_resolves_first_then_captures_current_goal() -> None:
    clock = TickClock()
    provider = DeterministicProvider(
        (
            json.dumps(
                {
                    "rationale": "single bounded reasoning step",
                    "steps": [
                        {
                            "id": "s1",
                            "title": "Analyze",
                            "description": "Analyze the requested relation.",
                            "dependencies": [],
                            "risk": "read_only",
                        }
                    ],
                }
            ),
        )
    )
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    inputs = RunInputs(
        goal=_goal(),
        tenant_id="tenant",
        user_id="user",
        workspace_id="workspace",
        session_id="session",
        run_id="run-1",
    )
    namespace = inputs.namespace

    assert runtime.memory_cards.store.namespace_cards(namespace) == ()
    state = runtime._new_state("run-1", inputs)
    runtime._plan(state)

    cards = runtime.memory_cards.store.namespace_cards(namespace)
    assert len(cards) == 1
    card = cards[0]
    assert card.content == inputs.goal.objective
    assert card.metadata["captured_run_id"] == "run-1"
    assert card.metadata["capture_boundary"] == "after_initial_plan_resolution"
    assert card.metadata["domain"] == "narrative-game-analysis"
    assert card.metadata["is_evidence"] is False

    assert provider.requests
    first_request_text = "\n".join(
        message.content for message in provider.requests[0].messages
    )
    assert "<scientific_nuance_workbench>" in first_request_text

    # The planner had to resolve before capture. The only card is explicitly
    # tagged as being created after the planning-resolution boundary.
    assert runtime.scientific_summary()["invariants"]["capture_after_initial_resolution"] is True


def test_scientific_runtime_does_not_expose_current_goal_as_preplan_memory() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    inputs = RunInputs(
        goal=_goal(),
        tenant_id="tenant",
        user_id="user",
        workspace_id="workspace",
        session_id="session",
        run_id="run-no-self-memory",
    )

    runtime._new_state("run-no-self-memory", inputs)
    hits = runtime.memory.retriever.search(
        inputs.namespace,
        inputs.goal.objective,
        limit=20,
        include_parent=True,
    )

    assert all(hit.record.source != "run-goal" for hit in hits)
    assert runtime.memory_cards.store.namespace_cards(inputs.namespace) == ()
    assert (
        runtime.scientific_summary()["invariants"][
            "run_goal_memory_deferred_until_after_first_retrieval"
        ]
        is True
    )


def test_scientific_runtime_does_not_capture_from_initial_checkpoint() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    inputs = RunInputs(
        goal=_goal(),
        tenant_id="tenant",
        user_id="user",
        workspace_id="workspace",
        session_id="session",
        run_id="run-initial-checkpoint",
    )

    runtime._new_state("run-initial-checkpoint", inputs)
    checkpoint = runtime.checkpointer.latest("run-initial-checkpoint")
    assert checkpoint is not None
    assert checkpoint.plan is None
    assert runtime.memory_cards.store.namespace_cards(inputs.namespace) == ()

    restored = runtime._state_from_checkpoint(inputs, checkpoint)

    assert restored.plan is None
    assert runtime.memory_cards.store.namespace_cards(inputs.namespace) == ()
    assert (
        runtime.scientific_summary()["invariants"][
            "resume_requires_accepted_plan_before_capture"
        ]
        is True
    )


def test_scientific_runtime_shares_one_memory_and_relational_plane() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )

    assert runtime.context_resolver.memory is runtime.memory
    assert runtime.scientific_context.resolver is runtime.context_resolver
    assert runtime.nuance_runtime.resolver is runtime.context_resolver
    assert runtime.scientific_context.semantic_plane is runtime.semantic_plane
    assert runtime.lens_lab is runtime.semantic_plane.governance.registry.lab
    assert runtime.context_resolver.cards is runtime.memory_cards
    assert runtime.context_resolver.relations is runtime.relational_memory
    summary = runtime.scientific_summary()
    assert summary["semantic_plane_fingerprint"] == runtime.semantic_plane.fingerprint
    assert summary["semantic_lens_count"] >= 100
    assert summary["invariants"]["semantic_plane_is_governed"] is True


def test_scientific_runtime_exposes_governed_semantic_analysis() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    observations = (
        SemanticObservation(
            "runtime-semantic-1",
            "The deployment shows concept drift after a regime switch.",
            0,
            evidence_ids=("ev-runtime",),
            tags=("concept drift", "regime"),
        ),
        SemanticObservation(
            "runtime-semantic-2",
            "Conditional accuracy degrades while covariate coverage remains.",
            1,
            evidence_ids=("ev-runtime",),
            tags=("target", "mapping"),
        ),
        SemanticObservation(
            "runtime-semantic-3",
            "A later window preserves the changed predictor-target relation.",
            2,
            evidence_ids=("ev-runtime",),
            tags=("drift", "relationship changed"),
        ),
    )
    finding = SemanticFinding(
        finding_id="runtime-drift",
        lens_key="concept_drift",
        family=LensFamily.PREDICTIVE,
        observation_ids=("runtime-semantic-1",),
        interpretation="Concept drift is a candidate explanation.",
        prediction="The held-out deployment window will preserve the drift.",
        confidence=0.80,
        ambiguity=0.20,
        novelty=0.60,
        evidence_ids=("ev-runtime",),
    )

    snapshot = runtime.analyze_semantics(
        observations,
        findings=(finding,),
        requested=("concept_drift",),
        domain="narrative-game-analysis",
    )

    assert snapshot.semantic_domain == "narrative-game-analysis"
    assert snapshot.governance.domain == "narrative-game-analysis"
    assert snapshot.forecasts
    assert snapshot.target_fusions
    assert snapshot.factual_assertion_authorized is False
    assert snapshot.causal_assertion_authorized is False


def test_scientific_runtime_can_share_lens_lab_and_preserves_result_metadata() -> None:
    clock = TickClock()
    lab = ScientificLensLab()
    provider = DeterministicProvider(("unused",))
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        lens_lab=lab,
        wall_clock=clock,
        monotonic=clock,
    )
    result = AgentResult(
        run_id="run-science-result",
        goal_id="goal-1",
        success=True,
        reason=TerminationReason.GOAL_REACHED,
        answer="done",
        usage=Usage(),
        metadata={
            "scientific": {"caller_owned": True},
            "existing": 7,
        },
    )

    decorated = runtime._decorate_scientific_result(result)

    assert runtime.lens_lab is lab
    assert runtime.semantic_plane.governance.registry.lab is lab
    assert decorated.metadata["scientific"] == {"caller_owned": True}
    assert decorated.metadata["existing"] == 7
    assert "jeeves_scientific" in decorated.metadata
    summary = decorated.metadata["jeeves_scientific"]
    assert summary["semantic_plane_fingerprint"] == runtime.semantic_plane.fingerprint
    assert summary["invariants"]["semantic_calibration_retains_forecast_custody"] is True


def test_scientific_runtime_rebinds_relations_to_supplied_resolver_cards() -> None:
    clock = TickClock()
    memory = MemoryManager(clock=clock)
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0), clock=clock)
    resolver = LayeredContextResolver(
        cards=cards,
        memory=memory,
        relations=None,
        policy=ResolutionPolicy(minimum_item_score=0.0, maximum_tier=1),
    )
    provider = DeterministicProvider(("unused",))
    runtime = ScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        memory=memory,
        context_resolver=resolver,
        wall_clock=clock,
        monotonic=clock,
    )

    assert runtime.memory_cards is cards
    assert runtime.relational_memory.cards is cards
    assert resolver.relations is runtime.relational_memory
