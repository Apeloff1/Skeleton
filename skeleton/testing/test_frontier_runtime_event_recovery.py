from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime, ExecutionResult
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent, EventBus, SQLiteEventJournal
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.runtime_events import (
    execution_event_to_memory_item,
    execution_result_to_event,
)


class RecoveryAgent:
    name = "recovery-agent"
    capabilities = {"runtime.recover", "memory.write"}

    async def run(self, task, context=None):
        return {"task": task, "context": dict(context or {}), "status": "ok"}


def test_runtime_event_survives_reopen_and_replays_into_persistent_memory(tmp_path):
    async def scenario():
        runtime = AgentRuntime()
        runtime.register(RecoveryAgent())
        result = await runtime.execute(
            "recovery-agent",
            "persist frontier execution outcome",
            context={"wave": 6},
            required_capabilities={"runtime.recover", "memory.write"},
            source_repository="Apeloff1/gameforge-rs",
            source_revision="481fcfca5a23272b70353eb09b7c3406bbc9bdd9",
            source_path="crates/gf-core/src/lib.rs",
            idempotency_key="runtime-request-42",
        )
        duplicate = await runtime.execute(
            "recovery-agent",
            "persist frontier execution outcome",
            context={"wave": 6},
            required_capabilities={"runtime.recover", "memory.write"},
            source_repository="Apeloff1/gameforge-rs",
            source_revision="481fcfca5a23272b70353eb09b7c3406bbc9bdd9",
            source_path="crates/gf-core/src/lib.rs",
            idempotency_key="runtime-request-42",
        )

        event = execution_result_to_event(result)
        duplicate_event = execution_result_to_event(duplicate)
        assert event.payload["execution_identity_sha256"] == duplicate_event.payload[
            "execution_identity_sha256"
        ]
        assert event.payload["idempotency_key_sha256"] == stable_content_digest(
            "runtime-request-42"
        )
        assert event.payload["provenance"]["source_repository"] == "Apeloff1/gameforge-rs"

        journal_path = tmp_path / "runtime-events.sqlite3"
        journal = SQLiteEventJournal(journal_path)
        try:
            bus = EventBus(journal=journal)
            assert await bus.publish(event) == 0
            assert await journal.pending_count() == 1
        finally:
            journal.close()

        memory_path = tmp_path / "runtime-memory.sqlite3"
        reopened_journal = SQLiteEventJournal(journal_path)
        collection = SQLiteCollection(memory_path, namespace="runtime-outcomes")
        try:
            memory = CollectionMemoryAdapter(collection)
            recovered = EventBus(journal=reopened_journal)

            async def persist(event):
                await memory.put(execution_event_to_memory_item(event))

            await recovered.subscribe("runtime.completed", persist)
            assert await recovered.replay_pending() == 1
            assert await reopened_journal.pending_count() == 0
        finally:
            reopened_journal.close()
            collection.close()

        reopened_memory = SQLiteCollection(memory_path, namespace="runtime-outcomes")
        try:
            memory = CollectionMemoryAdapter(reopened_memory)
            hits = await memory.search(
                "runtime.completed recovery-agent",
                filters={"agent": "recovery-agent"},
            )
            assert len(hits) == 1
            metadata = hits[0]["metadata"]
            assert metadata["execution_identity_sha256"] == event.payload[
                "execution_identity_sha256"
            ]
            assert metadata["artifact_sha256"] == result.provenance.content_sha256
            assert metadata["idempotency_key_sha256"] == stable_content_digest(
                "runtime-request-42"
            )
            assert metadata["source_repository"] == "Apeloff1/gameforge-rs"
        finally:
            reopened_memory.close()

    asyncio.run(scenario())


def test_runtime_event_adapter_requires_provenance_and_aware_timestamps():
    now = datetime.now(timezone.utc)
    missing_provenance = ExecutionResult(
        task="task",
        agent="agent",
        started_at=now,
        finished_at=now,
        output={"ok": True},
    )
    with pytest.raises(ValueError, match="requires provenance"):
        execution_result_to_event(missing_provenance)


def test_runtime_memory_adapter_rejects_non_runtime_or_incomplete_events():
    with pytest.raises(ValueError, match="runtime outcome event"):
        execution_event_to_memory_item(DomainEvent.create("world.updated", {"value": 1}))

    incomplete = DomainEvent.create(
        "runtime.completed",
        {
            "execution_identity_sha256": "execution",
            "agent": "agent",
            "artifact_sha256": "",
            "provenance": {},
        },
    )
    with pytest.raises(ValueError, match="requires execution identity"):
        execution_event_to_memory_item(incomplete)
