from __future__ import annotations

import json

import pytest

from skeleton.jeeves.agent.cognition import ContextCompiler
from skeleton.jeeves.agent.context_fabric import (
    CallableContextAdapter,
    CognitiveContextFabric,
    ContextFabricPolicy,
    DeepContextRecord,
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
from skeleton.jeeves.agent.types import Goal, MemoryKind, stable_fingerprint


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


def _fabric_payload(packet) -> dict:
    section = next(section for section in packet.sections if section.name == "context_fabric")
    return json.loads(section.content)


def _external_record(
    *,
    content: str = "Canonical external alpha clue.",
    fingerprint: str | None = None,
) -> DeepContextRecord:
    return DeepContextRecord(
        source_tier=SourceTier.EXTERNAL,
        source_ref="external-alpha",
        source_provider="test-external",
        source_fingerprint=fingerprint or stable_fingerprint(content),
        content=content,
        canonical=True,
        trust=0.92,
        confidence=0.88,
        salience=0.80,
        token_estimate=12,
        tags=("alpha", "canonical"),
        metadata={"fixture": True},
    )


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


def test_fabric_deduplicates_memory_already_present_in_base_context() -> None:
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

    assert record.memory_id in packet.memory_ids
    payload = _fabric_payload(packet)
    assert payload["records"] == []
    assert payload["contract"]["records_are_not_evidence_by_inclusion"] is True
    assert payload["contract"]["evidence_ledger_remains_authoritative"] is True
    snapshot = compiler.last_fabric_snapshot()
    assert snapshot["ok"] is True
    assert snapshot["record_count"] >= 1


def test_external_canonical_adapter_reaches_context_without_becoming_evidence() -> None:
    clock = TickClock()
    namespace = _namespace()
    memory = MemoryManager(clock=clock)
    record = _external_record()
    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=8,
            maximum_tokens=2_000,
            minimum_deep_trust=0.35,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    adapter = CallableContextAdapter(
        SourceTier.EXTERNAL,
        fetcher=lambda ns, refs, max_records, max_tokens: (
            (record,) if record.source_ref in refs else ()
        ),
        searcher=lambda ns, query, max_records, max_tokens: (record,),
        source_provider=record.source_provider,
    )
    fabric.register(adapter)
    compiler = FabricContextCompiler(fabric=fabric)

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(clock=clock),
    )

    payload = _fabric_payload(packet)
    assert len(payload["records"]) == 1
    row = payload["records"][0]
    assert row["source_ref"] == record.source_ref
    assert row["source_provider"] == "test-external"
    assert row["content"] == record.content
    assert row["canonical"] is True
    assert payload["contract"]["records_are_not_evidence_by_inclusion"] is True
    assert all(item["factual_assertion_authorized"] is False for item in payload["lens_governance"])
    assert all(item["causal_assertion_authorized"] is False for item in payload["lens_governance"])
    assert packet.evidence_ids == ()


def test_stale_index_card_is_reported_when_canonical_fingerprint_changes() -> None:
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
    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=8,
            maximum_tokens=2_000,
            minimum_deep_trust=0.35,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    stale_card = fabric.index_record(namespace.key, old, cue="alpha clue")
    fabric.register(
        CallableContextAdapter(
            SourceTier.EXTERNAL,
            fetcher=lambda ns, refs, max_records, max_tokens: (
                (current,) if current.source_ref in refs else ()
            ),
            searcher=lambda ns, query, max_records, max_tokens: (current,),
            source_provider=current.source_provider,
        )
    )
    compiler = FabricContextCompiler(fabric=fabric)

    packet = compiler.compile(
        system_instruction="Use evidence carefully.",
        task_instruction="Build a bounded plan.",
        goal=_goal(),
        namespace=namespace,
        memory=MemoryManager(clock=clock),
        evidence=EvidenceLedger(clock=clock),
    )

    payload = _fabric_payload(packet)
    assert stale_card.card_id in payload["stale_card_ids"]
    assert payload["contract"]["stale_index_cards_are_not_canonical"] is True
    assert any(row["source_fingerprint"] == current.source_fingerprint for row in payload["records"])


def test_optional_fabric_failure_falls_back_to_base_context_and_is_observable() -> None:
    compiler = FabricContextCompiler(
        fabric=ExplodingFabric(),
        fabric_policy=FabricCompilerPolicy(fail_closed=False),
    )

    packet = _compile(compiler)

    assert "goal" in packet.retained_sections
    assert "context_fabric" not in {section.name for section in packet.sections}
    snapshot = compiler.last_fabric_snapshot()
    assert snapshot["ok"] is False
    assert "synthetic fabric failure" in snapshot["error"]


def test_required_fabric_failure_fails_closed() -> None:
    compiler = FabricContextCompiler(
        fabric=ExplodingFabric(),
        fabric_policy=FabricCompilerPolicy(fail_closed=True),
    )

    with pytest.raises(RuntimeError, match="synthetic fabric failure"):
        _compile(compiler)


def test_fabric_index_recall_is_not_accidentally_filtered_by_runtime_tags() -> None:
    clock = TickClock()
    namespace = _namespace()
    record = _external_record()
    fabric = CognitiveContextFabric(
        policy=ContextFabricPolicy(
            deep_limit=8,
            maximum_tokens=2_000,
            minimum_deep_trust=0.35,
            minimum_fast_hits_before_skip_deep=1,
        )
    )
    calls = {"search": 0, "fetch": 0}

    def fetcher(ns, refs, max_records, max_tokens):
        calls["fetch"] += 1
        return (record,) if record.source_ref in refs else ()

    def searcher(ns, query, max_records, max_tokens):
        calls["search"] += 1
        return (record,)

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

    payload = _fabric_payload(second)
    assert calls["fetch"] >= 1
    assert payload["fast_recall_fingerprint"]
    assert compiler.last_fabric_snapshot()["ok"] is True
    assert calls["search"] >= first_searches
