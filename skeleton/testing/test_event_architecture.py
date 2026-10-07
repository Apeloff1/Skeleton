from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.frontier.runtime.event_architecture import (
    EventCompatibilityError,
    EventCompatibilityRegistry,
    EventRetentionPolicy,
    EventSchemaContract,
)
from skeleton.frontier.runtime.operation_stream import ReplayCursor, StreamReplayGapError
from skeleton.frontier.runtime.operation_stream_store import SQLiteOperationEventStore


def test_event_schema_contract_requires_deterministic_upgrade_path() -> None:
    contract = EventSchemaContract(
        event_type="operation.progress",
        current_version=3,
        readable_versions=(1, 2, 3),
        writable_versions=(3,),
        upgrade_edges=((1, 2), (2, 3)),
    )

    assert contract.upgrade_path(1) == (1, 2, 3)
    assert contract.upgrade_path(2) == (2, 3)
    assert contract.upgrade_path(3) == (3,)
    contract.assert_readable(1)
    contract.assert_writable(3)

    with pytest.raises(EventCompatibilityError, match="not writable"):
        contract.assert_writable(1)


def test_event_schema_contract_rejects_readable_version_without_upgrade_path() -> None:
    with pytest.raises(EventCompatibilityError, match="no upgrade path"):
        EventSchemaContract(
            event_type="operation.progress",
            current_version=3,
            readable_versions=(1, 3),
            writable_versions=(3,),
            upgrade_edges=(),
        )


def test_event_registry_rejects_conflicting_authority_for_same_event_type() -> None:
    first = EventSchemaContract(
        event_type="operation.completed",
        current_version=2,
        readable_versions=(1, 2),
        writable_versions=(2,),
        upgrade_edges=((1, 2),),
    )
    registry = EventCompatibilityRegistry((first,))

    registry.register(first)
    assert registry.event_types == ("operation.completed",)

    conflicting = EventSchemaContract(
        event_type="operation.completed",
        current_version=3,
        readable_versions=(2, 3),
        writable_versions=(3,),
        upgrade_edges=((2, 3),),
    )
    with pytest.raises(EventCompatibilityError, match="different contract"):
        registry.register(conflicting)


def test_retention_policy_never_invents_acknowledgement() -> None:
    policy = EventRetentionPolicy(minimum_retained_events=2)

    decision = policy.plan(
        compacted_through=1,
        latest_sequence=8,
        acknowledged_through=None,
        terminal=False,
    )

    assert decision.compact_through == 1
    assert decision.replay_floor == 2
    assert decision.retained_events == 7


def test_retention_policy_bounds_compaction_by_ack_and_tail() -> None:
    policy = EventRetentionPolicy(
        minimum_retained_events=2,
        terminal_minimum_retained_events=0,
    )

    live = policy.plan(
        compacted_through=0,
        latest_sequence=10,
        acknowledged_through=9,
        terminal=False,
    )
    assert live.compact_through == 8
    assert live.replay_floor == 9
    assert live.retained_events == 2

    terminal = policy.plan(
        compacted_through=0,
        latest_sequence=10,
        acknowledged_through=10,
        terminal=True,
    )
    assert terminal.compact_through == 10
    assert terminal.replay_floor == 11
    assert terminal.retained_events == 0


def test_sqlite_retention_compaction_preserves_required_replay_tail(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    base = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
    policy = EventRetentionPolicy(minimum_retained_events=2)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        for index in range(1, 6):
            store.append(
                operation_id,
                "operation.progress",
                {"step": index},
                timestamp=base + timedelta(seconds=index),
            )
        store.register_consumer(
            operation_id,
            "client-a",
            lease_seconds=300,
            now=base,
        )
        store.acknowledge_consumer(
            operation_id,
            "client-a",
            5,
            lease_seconds=300,
            now=base + timedelta(seconds=1),
        )

        assert store.compact_with_retention(
            operation_id,
            policy,
            now=base + timedelta(seconds=2),
        ) == 3
        assert store.head(operation_id)["compacted_through"] == 3
        assert [
            event.sequence
            for event in store.replay(
                ReplayCursor(operation_id, after_sequence=3)
            )
        ] == [4, 5]

        with pytest.raises(StreamReplayGapError):
            store.replay(ReplayCursor(operation_id, after_sequence=2))


def test_sqlite_retention_compaction_requires_active_consumer_ack(
    tmp_path: Path,
) -> None:
    operation_id = str(uuid4())
    policy = EventRetentionPolicy(minimum_retained_events=0)

    with SQLiteOperationEventStore(tmp_path / "events.sqlite") as store:
        for index in range(1, 4):
            store.append(operation_id, "operation.progress", {"step": index})

        assert store.compact_with_retention(operation_id, policy) == 0
        assert store.head(operation_id)["compacted_through"] == 0
        assert [
            event.sequence
            for event in store.replay(ReplayCursor(operation_id))
        ] == [1, 2, 3]
