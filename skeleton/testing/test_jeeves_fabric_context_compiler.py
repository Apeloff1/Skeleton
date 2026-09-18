from __future__ import annotations

import json

import pytest

from skeleton.jeeves.agent.cognition import (
    ContextBudget,
    ContextCompiler,
    MemoryContextPolicy,
)
from skeleton.jeeves.agent.context_fabric import (
    CallableContextAdapter,
    CognitiveContextFabric,
    ContextFabricPolicy,
    DeepContextRecord,
    MemoryManagerAdapter,
)
from skeleton.jeeves.agent.evidence import EvidenceLedger
from skeleton.jeeves.agent.fabric_cognition import (
    FabricCompilerPolicy,
    FabricContextCompiler,
)
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game_index import SourceTier
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import JeevesAgentRuntime
from skeleton.jeeves.agent.types import (
    AgentContractError,
    Goal,
    MemoryKind,
    stable_fingerprint,
)


class TickClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


class ExplodingFabric(CognitiveContextFabric):
    def retrieve(self, *args, **kwargs):
        raise RuntimeError("synthetic fabric failure")


def _namespace() -> MemoryNamespace:
    return MemoryNamespace("tenant", "user", "workspace", "session")


def _goal() -> Goal:
    return Goal(
        "goal-fabric",
        "Compare the remembered alpha clue with the current evidence.",
        metadata={"domain": "context-fabric-test"},
    )


def _compile(
    compiler: ContextCompiler,
    *,
    memory: MemoryManager | None = None,
    namespace: MemoryNamespace | None = None,
):
    clock = TickClock()
    selected_memory = memory or MemoryManager(clock=clock)
    selected_namespace = namespace or _namespace()
    return compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=selected_namespace,
        memory=selected_memory,
        evidence=EvidenceLedger(clock=clock),
    )


def _section(packet, name: str):
    return next(section for section in packet.sections if section.name == name)


def _payload(packet, name: str):
    section = _section(packet, name)
    return section, json.loads(section.content)


def _external_record(
    *,
    content: str = "Canonical external alpha clue.",
    fingerprint: str | None = None,
    source_ref: str = "external-alpha",
    provider: str = "test-external",
    token_estimate: int = 12,
) -> DeepContextRecord:
    return DeepContextRecord(
        source_tier=SourceTier.EXTERNAL,
        source_ref=source_ref,
        source_provider=provider,
        source_fingerprint=fingerprint or stable_fingerprint((provider, source_ref, content)),
        content=content,
        canonical=True,
        trust=0.92,
        confidence=0.88,
        salience=0.80,
        token_estimate=token_estimate,
        tags=("alpha", "canonical"),
        metadata={"fixture": True},
    )


def _external_fabric(record: DeepContextRecord) -> CognitiveContextFabric:
    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=8,
            maximum_tokens=2_000,
            minimum_deep_trust=0.35,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    fabric.register(
        CallableContextAdapter(
            SourceTier.EXTERNAL,
            fetcher=lambda ns, refs, max_records, max_tokens: (
                (record,) if record.source_ref in refs else ()
            ),
            searcher=lambda ns, query, max_records, max_tokens: (record,),
            source_provider=record.source_provider,
        )
    )
    return fabric


def test_default_runtime_uses_fabric_compiler_but_explicit_compiler_is_preserved() -> None:
    clock = TickClock()
    provider = DeterministicProvider(("unused",))
    runtime = JeevesAgentRuntime(
        provider_router=ProviderRouter((provider,), clock=clock),
        wall_clock=clock,
        monotonic=clock,
    )
    assert isinstance(runtime.context, FabricContextCompiler)

    custom = ContextCompiler()
    explicit = JeevesAgentRuntime(
        provider_router=ProviderRouter(
            (DeterministicProvider(("unused",), name="explicit"),),
            clock=clock,
        ),
        context_compiler=custom,
        wall_clock=clock,
        monotonic=clock,
    )
    assert explicit.context is custom


def test_base_context_compiler_restores_explicit_fabric_contract() -> None:
    clock = TickClock()
    namespace = _namespace()
    memory = MemoryManager(clock=clock)
    record = memory.remember(
        namespace,
        "User prefers evidence-first deterministic compiler validation.",
        kind=MemoryKind.EPISODIC,
        trust=1.0,
        salience=0.9,
        source="user-interaction",
        tags=("compiler", "evidence"),
    )
    fabric = CognitiveContextFabric()
    fabric.index_record(
        namespace.key,
        DeepContextRecord(
            source_tier=SourceTier.MEMORY_STORE,
            source_ref=record.memory_id,
            source_provider=f"memory-store:{namespace.key}",
            source_fingerprint=record.fingerprint,
            content=record.content,
            canonical=True,
            trust=record.trust,
            confidence=record.trust,
            salience=record.salience,
            token_estimate=max(1, len(record.content) // 4),
            tags=record.tags,
        ),
        cue=record.content,
    )

    packet = ContextCompiler().compile(
        system_instruction="system",
        task_instruction="plan the compiler work",
        goal=Goal("goal-context-fabric-explicit", "deterministic compiler evidence"),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
        context_fabric=fabric,
    )

    names = set(packet.retained_sections)
    assert {"fast_memory_index", "canonical_context", "semantic_lenses"} <= names
    assert "memory" not in names

    fast_section, fast_rows = _payload(packet, "fast_memory_index")
    canonical_section, canonical_rows = _payload(packet, "canonical_context")
    _, semantic = _payload(packet, "semantic_lenses")

    assert canonical_section.priority > fast_section.priority
    assert record.content not in fast_section.content
    assert fast_rows[0]["authoritative"] is False
    assert fast_rows[0]["purpose"] == "retrieval-index-only"
    assert record.memory_id in canonical_section.content
    assert any(row["content"] == record.content for row in canonical_rows)
    assert semantic["interpretive_only"] is True
    assert all(row["scientific_grade"] for row in semantic["lenses"])
    assert all("permissions" in row for row in semantic["lenses"])
    assert all(row["evidence_ceiling"] for row in semantic["lenses"])
    assert all(row["factual_assertion_authorized"] is False for row in semantic["lenses"])
    assert all(row["causal_assertion_authorized"] is False for row in semantic["lenses"])
    assert "not factual evidence" in semantic["instruction"]


def test_fabric_replaces_legacy_memory_with_canonical_rehydration() -> None:
    clock = TickClock()
    namespace = _namespace()
    memory = MemoryManager(clock=clock)
    record = memory.remember(
        namespace,
        "The alpha clue was observed in the prior turn.",
        kind=MemoryKind.EPISODIC,
        trust=0.95,
        salience=0.90,
        source="fixture",
        tags=("alpha",),
    )
    compiler = FabricContextCompiler()

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
    )

    names = {section.name for section in packet.sections}
    assert "memory" not in names
    assert "canonical_context" in names
    assert record.memory_id in packet.memory_ids

    _, canonical = _payload(packet, "canonical_context")
    assert any(row["source_ref"] == record.memory_id for row in canonical)
    assert any(row["content"] == record.content for row in canonical)
    snapshot = compiler.last_fabric_snapshot()
    assert snapshot["ok"] is True
    assert snapshot["record_count"] >= 1


def test_external_canonical_adapter_reaches_context_without_becoming_evidence() -> None:
    clock = TickClock()
    namespace = _namespace()
    record = _external_record()
    compiler = FabricContextCompiler(fabric=_external_fabric(record))

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=MemoryManager(clock=clock),
        evidence=EvidenceLedger(clock=clock),
    )

    _, canonical = _payload(packet, "canonical_context")
    row = next(item for item in canonical if item["source_ref"] == record.source_ref)
    assert row["source_provider"] == record.source_provider
    assert row["content"] == record.content
    assert row["canonical"] is True

    _, semantic = _payload(packet, "semantic_lenses")
    assert semantic["interpretive_only"] is True
    assert all(item["factual_assertion_authorized"] is False for item in semantic["lenses"])
    assert all(item["causal_assertion_authorized"] is False for item in semantic["lenses"])
    assert packet.evidence_ids == ()


def test_stale_index_card_is_reported_and_canonical_content_wins() -> None:
    clock = TickClock()
    namespace = _namespace()
    old = _external_record(
        content="Old alpha clue.",
        fingerprint=stable_fingerprint("old-alpha"),
    )
    current = _external_record(
        content="Updated canonical alpha clue.",
        fingerprint=stable_fingerprint("new-alpha"),
    )
    fabric = _external_fabric(current)
    stale_card = fabric.index_record(namespace.key, old, cue="alpha clue")
    compiler = FabricContextCompiler(fabric=fabric)

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=MemoryManager(clock=clock),
        evidence=EvidenceLedger(clock=clock),
    )

    _, semantic = _payload(packet, "semantic_lenses")
    _, canonical = _payload(packet, "canonical_context")
    assert stale_card.card_id in semantic["stale_card_ids"]
    assert any(row["source_fingerprint"] == current.source_fingerprint for row in canonical)
    assert all(row["content"] != old.content for row in canonical)


def test_optional_fabric_failure_falls_back_to_base_context_and_is_observable() -> None:
    compiler = FabricContextCompiler(
        fabric=ExplodingFabric(),
        fabric_policy=FabricCompilerPolicy(fail_closed=False),
    )

    packet = _compile(compiler)

    assert "goal" in packet.retained_sections
    names = {section.name for section in packet.sections}
    assert "fast_memory_index" not in names
    assert "canonical_context" not in names
    assert "semantic_lenses" not in names
    snapshot = compiler.last_fabric_snapshot()
    assert snapshot["ok"] is False
    assert "synthetic fabric failure" in snapshot["error"]


def test_non_fabric_compiler_failure_is_not_hidden_by_fail_open_mode() -> None:
    class BrokenRenderer(FabricContextCompiler):
        def _render_context_fabric(self, result):
            raise ValueError("synthetic renderer bug")

    compiler = BrokenRenderer(
        fabric=_external_fabric(_external_record()),
        fabric_policy=FabricCompilerPolicy(fail_closed=False),
    )

    with pytest.raises(ValueError, match="synthetic renderer bug"):
        _compile(compiler)


def test_required_fabric_failure_fails_closed() -> None:
    compiler = FabricContextCompiler(
        fabric=ExplodingFabric(),
        fabric_policy=FabricCompilerPolicy(fail_closed=True),
    )

    with pytest.raises(RuntimeError, match="synthetic fabric failure"):
        _compile(compiler)


def test_indexed_deep_result_is_used_by_next_fast_pass_without_tag_filtering() -> None:
    clock = TickClock()
    namespace = _namespace()
    record = _external_record()
    calls = {"search": 0, "fetch": 0}

    def fetcher(ns, refs, max_records, max_tokens):
        calls["fetch"] += 1
        return (record,) if record.source_ref in refs else ()

    def searcher(ns, query, max_records, max_tokens):
        calls["search"] += 1
        return (record,)

    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=8,
            maximum_tokens=2_000,
            minimum_deep_trust=0.35,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    fabric.register(
        CallableContextAdapter(
            SourceTier.EXTERNAL,
            fetcher=fetcher,
            searcher=searcher,
            source_provider=record.source_provider,
        )
    )
    compiler = FabricContextCompiler(fabric=fabric)
    memory = MemoryManager(clock=clock)

    compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
    )
    first_searches = calls["search"]

    second = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
    )

    _, fast_rows = _payload(second, "fast_memory_index")
    assert fast_rows
    assert any(row["source_ref"] == record.source_ref for row in fast_rows)
    assert calls["fetch"] >= 1
    assert calls["search"] >= first_searches
    assert compiler.last_fabric_snapshot()["ok"] is True


def test_deep_context_record_rejects_invalid_token_estimates() -> None:
    for value in (0, -1, True):
        with pytest.raises(AgentContractError, match="token_estimate"):
            DeepContextRecord(
                source_tier=SourceTier.EXTERNAL,
                source_ref="invalid-token-record",
                source_provider="provider-a",
                source_fingerprint=stable_fingerprint(("invalid", value)),
                content="invalid token estimate",
                canonical=True,
                trust=0.8,
                confidence=0.8,
                salience=0.8,
                token_estimate=value,
            )


def test_wrong_provider_same_ref_does_not_resolve_provider_bound_card() -> None:
    namespace = _namespace()
    indexed = _external_record(
        content="Provider A indexed content.",
        source_ref="shared-provider-ref",
        provider="provider-a",
    )
    wrong = _external_record(
        content="Provider B different canonical content.",
        source_ref="shared-provider-ref",
        provider="provider-b",
    )
    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=4,
            maximum_tokens=1_000,
            minimum_deep_trust=0.0,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    fabric.index_record(namespace.key, indexed, cue="shared provider ref")
    fabric.register(
        CallableContextAdapter(
            SourceTier.EXTERNAL,
            fetcher=lambda ns, refs, max_records, max_tokens: (wrong,),
            searcher=lambda ns, query, max_records, max_tokens: (wrong,),
            source_provider="provider-b",
        )
    )

    result = fabric.retrieve(namespace.key, "shared provider ref")

    assert "shared-provider-ref" in result.unresolved_source_refs
    assert any(record.source_provider == "provider-b" for record in result.records)


def test_context_dedupe_preserves_provider_identity_for_same_source_ref() -> None:
    left = _external_record(
        content="Provider A canonical content.",
        source_ref="shared-ref",
        provider="provider-a",
    )
    right = _external_record(
        content="Provider B canonical content.",
        source_ref="shared-ref",
        provider="provider-b",
    )

    packed = CognitiveContextFabric._dedupe((left, right))

    assert len(packed) == 2
    assert {record.source_provider for record in packed} == {"provider-a", "provider-b"}


def test_child_fabric_can_rehydrate_indexed_parent_memory_without_broad_search() -> None:
    clock = TickClock()
    child = _namespace()
    parent = child.parent()
    memory = MemoryManager(clock=clock)
    durable = memory.remember(
        parent,
        "durable alpha workspace memory",
        trust=0.95,
        salience=0.9,
        source="parent-fixture",
    )
    adapter = MemoryManagerAdapter(memory, child)
    deep_record = adapter.fetch_refs(
        child.key,
        (durable.memory_id,),
        max_records=4,
        max_tokens=1_000,
    )[0]
    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=4,
            maximum_tokens=1_000,
            minimum_deep_trust=0.0,
            minimum_fast_hits_before_skip_deep=1,
            broad_search_on_fast_fallback=False,
            broad_search_on_conflict=False,
        )
    )
    fabric.index_record(child.key, deep_record, cue="durable alpha workspace memory")

    result = fabric.retrieve(
        child.key,
        "durable alpha workspace memory",
        call_adapters=(adapter,),
    )

    assert result.broad_search_used is False
    assert any(record.source_ref == durable.memory_id for record in result.records)
    assert result.unresolved_source_refs == ()


def test_memory_adapter_parent_scope_cannot_read_session_private_records() -> None:
    clock = TickClock()
    child = _namespace()
    parent = child.parent()
    memory = MemoryManager(clock=clock)
    private = memory.remember(
        child,
        "shared alpha private session detail",
        trust=0.9,
        salience=0.8,
        source="private-fixture",
    )
    durable = memory.remember(
        parent,
        "shared alpha durable workspace detail",
        trust=0.9,
        salience=0.8,
        source="parent-fixture",
    )
    adapter = MemoryManagerAdapter(memory, child)

    parent_search = adapter.search(
        parent.key,
        "shared alpha detail",
        max_records=8,
        max_tokens=1_000,
    )
    parent_fetch = adapter.fetch_refs(
        parent.key,
        (private.memory_id, durable.memory_id),
        max_records=8,
        max_tokens=1_000,
    )
    child_fetch = adapter.fetch_refs(
        child.key,
        (private.memory_id, durable.memory_id),
        max_records=8,
        max_tokens=1_000,
    )

    assert {record.source_ref for record in parent_search} == {durable.memory_id}
    assert {record.source_ref for record in parent_fetch} == {durable.memory_id}
    assert {record.source_ref for record in child_fetch} == {
        private.memory_id,
        durable.memory_id,
    }


def test_memory_adapter_fetch_order_is_deterministic_and_respects_token_budget() -> None:
    clock = TickClock()
    namespace = _namespace()
    memory = MemoryManager(clock=clock)
    first = memory.remember(
        namespace,
        "first memory",
        trust=0.9,
        salience=0.8,
        source="fixture",
    )
    second = memory.remember(
        namespace,
        "second memory",
        trust=0.9,
        salience=0.8,
        source="fixture",
    )
    adapter = MemoryManagerAdapter(memory, namespace)

    ordered = adapter.fetch_refs(
        namespace.key,
        (second.memory_id, first.memory_id),
        max_records=2,
        max_tokens=100,
    )
    bounded = adapter.fetch_refs(
        namespace.key,
        (second.memory_id, first.memory_id),
        max_records=2,
        max_tokens=1,
    )

    assert [record.source_ref for record in ordered] == [
        second.memory_id,
        first.memory_id,
    ]
    assert bounded == ()


def test_callable_adapter_enforces_budget_even_when_callback_ignores_it() -> None:
    oversized = _external_record(
        content="oversized",
        source_ref="oversized",
        provider="provider-a",
        token_estimate=100,
    )
    small = _external_record(
        content="small",
        source_ref="small",
        provider="provider-a",
        token_estimate=5,
    )
    adapter = CallableContextAdapter(
        SourceTier.EXTERNAL,
        fetcher=lambda ns, refs, max_records, max_tokens: (oversized, small),
        searcher=lambda ns, query, max_records, max_tokens: (oversized, small),
        source_provider="provider-a",
    )

    values = adapter.search(
        _namespace().key,
        "alpha",
        max_records=2,
        max_tokens=10,
    )

    assert values == (small,)


def test_outer_fabric_rejects_oversized_record_from_noncompliant_adapter() -> None:
    oversized = _external_record(
        content="oversized outer record",
        source_ref="oversized-outer",
        provider="bad-provider",
        token_estimate=100,
    )

    class NoncompliantAdapter:
        source_tier = SourceTier.EXTERNAL
        source_provider = "bad-provider"

        def fetch_refs(self, namespace_key, source_refs, *, max_records, max_tokens):
            return (oversized,)

        def search(self, namespace_key, query, *, max_records, max_tokens):
            return (oversized,)

    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=4,
            maximum_tokens=10,
            minimum_deep_trust=0.0,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    fabric.register(NoncompliantAdapter())

    result = fabric.retrieve(_namespace().key, "oversized outer")

    assert result.records == ()
    assert result.token_estimate == 0


def test_canonical_and_semantic_sections_are_valid_json_within_memory_budget() -> None:
    clock = TickClock()
    namespace = _namespace()
    record = _external_record(
        content="x" * 8_000,
        source_ref="large-source",
        provider="provider-a",
        token_estimate=100,
    )
    compiler = FabricContextCompiler(
        fabric=_external_fabric(record),
        budget=ContextBudget(
            total_chars=12_000,
            system_chars=2_000,
            goal_chars=2_000,
            plan_chars=2_000,
            memory_chars=1_024,
            evidence_chars=2_000,
            observation_chars=2_000,
            scratch_chars=2_000,
        ),
        memory_policy=MemoryContextPolicy(
            limit=8,
            minimum_trust=0.35,
            include_parent_namespace=True,
            maximum_record_chars=512,
        ),
    )

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=MemoryManager(clock=clock),
        evidence=EvidenceLedger(clock=clock),
    )

    canonical_section, canonical = _payload(packet, "canonical_context")
    semantic_section, semantic = _payload(packet, "semantic_lenses")
    assert len(canonical_section.content) <= 1_024
    assert len(semantic_section.content) <= 1_024
    assert isinstance(canonical, list)
    assert isinstance(semantic, dict)
    assert canonical
    assert len(canonical[0]["content"]) <= 512
    assert tuple(row["source_ref"] for row in canonical) == canonical_section.source_ids
