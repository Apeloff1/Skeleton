from __future__ import annotations

import json

import pytest

from skeleton.jeeves.agent.relational_memory import RelationalMemoryIndex
from skeleton.jeeves.agent.context_pipeline import LayeredContextResolver, ResolutionPolicy
from skeleton.jeeves.agent.evidence import EvidenceLedger
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.nuance_runtime import (
    NuanceRuntimeError,
    ScientificContextCompiler,
)
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import RunInputs
from skeleton.jeeves.agent.scientific_runtime import (
    MaximalScientificJeevesRuntime,
    ScientificJeevesRuntime,
)
from skeleton.jeeves.agent.types import Goal


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
    return memory, cards, relations, resolver, ScientificContextCompiler(resolver)


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
    assert payload["contract"]["lens_predictive_influence_is_empirically_gated"] is True
    assert payload["contract"]["lens_hypergraphs_never_create_evidence"] is True
    assert payload["semantic_domain"] == "narrative-game-analysis"
    assert any(row["family"] == "film" for row in payload["lenses"])
    assert all("scientific_status" in row for row in payload["lenses"])
    assert all("global_predictive_weight" in row for row in payload["lenses"])
    assert all("predictive_weight" in row for row in payload["lenses"])
    assert all("domain_status" in row for row in payload["lenses"])
    assert all(row["factual_assertion_authorized"] is False for row in payload["lenses"])
    assert all(row["causal_assertion_authorized"] is False for row in payload["lenses"])
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
    assert runtime.context_resolver.cards is runtime.memory_cards
    assert runtime.context_resolver.relations is runtime.relational_memory
    summary = runtime.scientific_summary()
    assert "lens_science" in summary
    assert summary["maximal_semantics_enabled"] is False
    assert summary["semantic_lens_count"] >= 1
    assert summary["lens_science"]["invariants"]["semantic_lenses_remain_interpretive"] is True
    assert summary["lens_science"]["invariants"]["hypergraph_never_creates_evidence"] is True


def test_maximal_scientific_runtime_routes_extreme_rare_lenses() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = MaximalScientificJeevesRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    namespace = _namespace()
    runtime.nuance_runtime.prepare(
        namespace,
        "A shot reverse shot establishes a look across a dialogue cut.",
    )
    frame = runtime.nuance_runtime.prepare(
        namespace,
        "The reverse shot repeats the look and dialogue cut from a second viewpoint.",
        requested_lenses=("shot_reverse_shot_suture",),
        capture_interaction=False,
    )

    assert runtime.scientific_summary()["maximal_semantics_enabled"] is True
    assert runtime.nuance_runtime.semantic_registry.get(
        "shot_reverse_shot_suture"
    ).key == "shot_reverse_shot_suture"
    assert "shot_reverse_shot_suture" in {
        lens.key for lens in frame.lens_selection.lenses
    }
    governed = frame.lens_governance.record_for("shot_reverse_shot_suture")
    assert governed is not None
    assert governed.decision.factual_assertion_authorized is False
    assert governed.decision.causal_assertion_authorized is False


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
