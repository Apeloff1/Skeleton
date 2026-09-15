from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.agent_runtime import ExecutionResult
from skeleton.frontier.contracts import ProvenanceRecord, stable_content_digest
from skeleton.frontier.events import DomainEvent
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.runtime_events import (
    execution_event_to_memory_item,
    execution_result_to_event,
)


def _runtime_event() -> DomainEvent:
    started_at = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(seconds=2)
    output = {"status": "ok", "result": 7}
    idempotency_sha256 = stable_content_digest("runtime-integrity-7")
    provenance = ProvenanceRecord.for_artifact(
        source_repository="Apeloff1/gameforge-rs",
        source_revision="481fcfca5a23272b70353eb09b7c3406bbc9bdd9",
        source_path="crates/gf-core/src/lib.rs",
        operation="agent:integrity-agent",
        payload=output,
        metadata={"idempotency_key_sha256": idempotency_sha256},
    )
    result = ExecutionResult(
        task="persist integrity-bound outcome",
        agent="integrity-agent",
        started_at=started_at,
        finished_at=finished_at,
        output=output,
        provenance=provenance,
    )
    return execution_result_to_event(result)


def _tamper(event: DomainEvent, **updates: object) -> DomainEvent:
    payload = dict(event.payload)
    payload.update(updates)
    return DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )


def test_runtime_event_identity_rejects_tampered_agent():
    event = _runtime_event()
    with pytest.raises(ValueError, match="execution identity digest mismatch"):
        execution_event_to_memory_item(_tamper(event, agent="different-agent"))


def test_runtime_event_rejects_artifact_digest_that_disagrees_with_provenance():
    event = _runtime_event()
    with pytest.raises(ValueError, match="artifact digest disagrees with provenance"):
        execution_event_to_memory_item(
            _tamper(event, artifact_sha256="0" * 64)
        )


def test_runtime_event_rejects_idempotency_digest_that_disagrees_with_provenance():
    event = _runtime_event()
    with pytest.raises(ValueError, match="idempotency digest disagrees with provenance"):
        execution_event_to_memory_item(
            _tamper(event, idempotency_key_sha256="1" * 64)
        )


def test_runtime_event_topic_must_match_succeeded_state():
    event = _runtime_event()
    with pytest.raises(ValueError, match="topic disagrees with succeeded state"):
        execution_event_to_memory_item(_tamper(event, succeeded=False))


def test_repeat_runtime_event_delivery_upserts_one_memory_item(tmp_path):
    async def scenario():
        event = _runtime_event()
        item = execution_event_to_memory_item(event)
        collection = SQLiteCollection(
            tmp_path / "runtime-integrity.sqlite3",
            namespace="runtime-integrity",
        )
        try:
            memory = CollectionMemoryAdapter(collection)
            assert await memory.put(item) == item["id"]
            assert await memory.put(item) == item["id"]
            assert collection.count() == 1

            hits = await memory.search(
                "runtime.completed integrity-agent",
                filters={"execution_identity_sha256": item["id"]},
            )
            assert len(hits) == 1
            assert hits[0]["id"] == item["id"]
            assert hits[0]["metadata"]["artifact_sha256"] == event.payload[
                "artifact_sha256"
            ]
        finally:
            collection.close()

    asyncio.run(scenario())
