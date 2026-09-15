from __future__ import annotations

import asyncio
from dataclasses import replace
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


TASK = "persist integrity-bound outcome"
AGENT = "integrity-agent"


def _runtime_result() -> ExecutionResult:
    started_at = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(seconds=2)
    output = {"status": "ok", "result": 7}
    idempotency_sha256 = stable_content_digest("runtime-integrity-7")
    provenance = ProvenanceRecord.for_artifact(
        source_repository="Apeloff1/gameforge-rs",
        source_revision="481fcfca5a23272b70353eb09b7c3406bbc9bdd9",
        source_path="crates/gf-core/src/lib.rs",
        operation="agent.execute.completed",
        payload=output,
        metadata={
            "agent": AGENT,
            "task": TASK,
            "required_capabilities": ["memory.write"],
            "agent_capabilities": ["memory.write", "runtime.recover"],
            "idempotency_key_sha256": idempotency_sha256,
        },
    )
    return ExecutionResult(
        task=TASK,
        agent=AGENT,
        started_at=started_at,
        finished_at=finished_at,
        output=output,
        provenance=provenance,
    )


def _runtime_event() -> DomainEvent:
    return execution_result_to_event(_runtime_result())


def _tamper(event: DomainEvent, **updates: object) -> DomainEvent:
    payload = dict(event.payload)
    payload.update(updates)
    return DomainEvent(
        topic=event.topic,
        payload=payload,
        occurred_at=event.occurred_at,
    )


def _tamper_provenance(event: DomainEvent, **updates: object) -> DomainEvent:
    provenance = dict(event.payload["provenance"])
    provenance.update(updates)
    return _tamper(event, provenance=provenance)


def test_runtime_event_identity_rejects_tampered_agent():
    event = _runtime_event()
    with pytest.raises(ValueError, match="agent disagrees with provenance"):
        execution_event_to_memory_item(_tamper(event, agent="different-agent"))


def test_runtime_event_rejects_artifact_digest_that_disagrees_with_provenance():
    event = _runtime_event()
    with pytest.raises(ValueError, match="artifact digest disagrees with provenance"):
        execution_event_to_memory_item(_tamper(event, artifact_sha256="0" * 64))


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


def test_runtime_event_operation_must_match_succeeded_state():
    event = _runtime_event()
    with pytest.raises(ValueError, match="operation disagrees with succeeded state"):
        execution_event_to_memory_item(
            _tamper_provenance(event, operation="agent.execute.failed")
        )


def test_runtime_event_task_digest_is_rebound_to_provenance_task():
    event = _runtime_event()
    provenance = dict(event.payload["provenance"])
    metadata = dict(provenance["metadata"])
    metadata["task"] = "different task"
    provenance["metadata"] = metadata

    with pytest.raises(ValueError, match="task digest disagrees with provenance"):
        execution_event_to_memory_item(_tamper(event, provenance=provenance))


def test_runtime_event_rejects_reversed_execution_window():
    event = _runtime_event()
    with pytest.raises(ValueError, match="finished_at must not precede started_at"):
        execution_event_to_memory_item(
            _tamper(
                event,
                started_at="2026-09-15T10:00:03+00:00",
                finished_at="2026-09-15T10:00:02+00:00",
            )
        )


def test_runtime_event_occurred_at_must_equal_finished_at():
    event = _runtime_event()
    shifted = DomainEvent(
        topic=event.topic,
        payload=event.payload,
        occurred_at=event.occurred_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="occurred_at must equal finished_at"):
        execution_event_to_memory_item(shifted)


def test_success_event_rejects_error_payload():
    event = _runtime_event()
    with pytest.raises(ValueError, match="must not contain an error"):
        execution_event_to_memory_item(_tamper(event, error="impossible"))


def test_producer_rejects_tampered_artifact_provenance():
    result = _runtime_result()
    assert result.provenance is not None
    tampered_provenance = replace(result.provenance, content_sha256="0" * 64)
    tampered = replace(result, provenance=tampered_provenance)

    with pytest.raises(ValueError, match="artifact digest does not match result"):
        execution_result_to_event(tampered)


def test_producer_rejects_reversed_execution_window():
    result = _runtime_result()
    tampered = replace(
        result,
        started_at=result.finished_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="finished_at must not precede started_at"):
        execution_result_to_event(tampered)


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
