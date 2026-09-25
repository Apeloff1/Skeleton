from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.memory_record import (
    MemoryContractError,
    MemoryKind,
    MemoryState,
    MemoryWriteProposal,
)
from skeleton.persistence.memory_repository import (
    MemoryConflict,
    MemoryNotFound,
    SQLiteMemoryRepository,
)


def _now() -> datetime:
    return datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)


def _proposal(
    *,
    key: str,
    tenant: str = "tenant-a",
    namespace: str = "assistant",
    subject: str = "user-a",
    content: str = "remember this",
    target: str | None = None,
    expected_version: int | None = None,
    expires_at: datetime | None = None,
) -> MemoryWriteProposal:
    return MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id=tenant,
        namespace=namespace,
        subject_id=subject,
        kind=MemoryKind.SEMANTIC,
        idempotency_key=key,
        proposed_at=_now(),
        content=content,
        provenance_refs=("conversation:thread-1",),
        source_operation_id=str(uuid4()),
        target_memory_id=target,
        expected_version=expected_version,
        expires_at=expires_at,
    )


def test_memory_proposal_requires_authoritative_payload() -> None:
    with pytest.raises(MemoryContractError, match="content or content_ref"):
        MemoryWriteProposal(
            proposal_id=str(uuid4()),
            tenant_id="tenant-a",
            namespace="assistant",
            subject_id="user-a",
            kind=MemoryKind.SEMANTIC,
            idempotency_key="k",
            proposed_at=_now(),
        )


def test_memory_proposal_rejects_expiry_before_creation() -> None:
    with pytest.raises(MemoryContractError, match="expires_at"):
        MemoryWriteProposal(
            proposal_id=str(uuid4()),
            tenant_id="tenant-a",
            namespace="assistant",
            subject_id="user-a",
            kind=MemoryKind.SEMANTIC,
            idempotency_key="k",
            proposed_at=_now(),
            content="x",
            expires_at=_now() - timedelta(seconds=1),
        )


def test_repository_reopens_durable_memory(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"
    first = SQLiteMemoryRepository(path)
    stored = first.commit(_proposal(key="create-1"), now=_now())
    first.close()

    reopened = SQLiteMemoryRepository(path)
    loaded = reopened.get(
        stored.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )

    assert loaded == stored
    assert loaded.version == 1
    assert loaded.state is MemoryState.ACTIVE


def test_namespace_and_tenant_isolation_fail_closed() -> None:
    repo = SQLiteMemoryRepository()
    stored = repo.commit(_proposal(key="create-1"), now=_now())

    with pytest.raises(MemoryNotFound):
        repo.get(stored.memory_id, tenant_id="tenant-b", namespace="assistant")
    with pytest.raises(MemoryNotFound):
        repo.get(stored.memory_id, tenant_id="tenant-a", namespace="other")


def test_exact_idempotent_replay_returns_same_record() -> None:
    repo = SQLiteMemoryRepository()
    proposal = _proposal(key="same-key")

    first = repo.commit(proposal, now=_now())
    replay = repo.commit(proposal, now=_now() + timedelta(seconds=5))

    assert replay == first
    assert len(
        repo.list_subject(
            tenant_id="tenant-a",
            namespace="assistant",
            subject_id="user-a",
        )
    ) == 1


def test_idempotency_key_reuse_with_different_payload_conflicts() -> None:
    repo = SQLiteMemoryRepository()
    first = _proposal(key="same-key", content="one")
    repo.commit(first, now=_now())
    conflicting = _proposal(key="same-key", content="two")

    with pytest.raises(MemoryConflict, match="idempotency_key"):
        repo.commit(conflicting, now=_now())


def test_optimistic_update_preserves_identity_and_increments_version() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create"), now=_now())

    updated = repo.commit(
        _proposal(
            key="update",
            content="new value",
            target=created.memory_id,
            expected_version=created.version,
        ),
        now=_now() + timedelta(seconds=1),
    )

    assert updated.memory_id == created.memory_id
    assert updated.version == 2
    assert updated.created_at == created.created_at
    assert updated.content == "new value"


def test_stale_update_is_rejected() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create"), now=_now())
    repo.commit(
        _proposal(
            key="update-1",
            content="v2",
            target=created.memory_id,
            expected_version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )

    with pytest.raises(MemoryConflict, match="version conflict"):
        repo.commit(
            _proposal(
                key="update-2",
                content="stale",
                target=created.memory_id,
                expected_version=1,
            ),
            now=_now() + timedelta(seconds=2),
        )


def test_tombstone_hides_memory_but_preserves_lineage() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create"), now=_now())

    deleted = repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now() + timedelta(seconds=1),
    )

    assert deleted.state is MemoryState.TOMBSTONED
    assert deleted.version == 2
    with pytest.raises(MemoryNotFound):
        repo.get(
            created.memory_id,
            tenant_id="tenant-a",
            namespace="assistant",
        )
    restored_view = repo.get(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        include_tombstoned=True,
    )
    assert restored_view.payload_digest == created.payload_digest


def test_old_idempotency_receipt_survives_later_versions_and_restart(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"
    repo = SQLiteMemoryRepository(path)
    create = _proposal(key="create", content="v1")
    created = repo.commit(create, now=_now())
    repo.commit(
        _proposal(
            key="update",
            content="v2",
            target=created.memory_id,
            expected_version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )
    repo.close()

    reopened = SQLiteMemoryRepository(path)
    replay = reopened.commit(create, now=_now() + timedelta(seconds=30))
    current = reopened.get(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )

    assert replay.version == 1
    assert replay.content == "v1"
    assert current.version == 2
    assert current.content == "v2"


def test_old_idempotency_key_cannot_be_reused_for_other_target_or_payload() -> None:
    repo = SQLiteMemoryRepository()
    original = _proposal(key="stable", content="v1")
    first = repo.commit(original, now=_now())
    second = repo.commit(_proposal(key="other", content="separate"), now=_now())

    with pytest.raises(MemoryConflict, match="different memory write intent"):
        repo.commit(
            _proposal(
                key="stable",
                content="v1",
                target=second.memory_id,
                expected_version=1,
            ),
            now=_now() + timedelta(seconds=2),
        )

    assert repo.get(
        first.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    ).content == "v1"


def test_expire_due_tombstones_only_elapsed_records() -> None:
    repo = SQLiteMemoryRepository()
    due = repo.commit(
        _proposal(
            key="due",
            content="old",
            expires_at=_now() + timedelta(seconds=5),
        ),
        now=_now(),
    )
    future = repo.commit(
        _proposal(
            key="future",
            content="new",
            expires_at=_now() + timedelta(seconds=50),
        ),
        now=_now(),
    )

    expired = repo.expire_due(
        tenant_id="tenant-a",
        namespace="assistant",
        now=_now() + timedelta(seconds=10),
    )

    assert [item.memory_id for item in expired] == [due.memory_id]
    assert expired[0].version == 2
    with pytest.raises(MemoryNotFound):
        repo.get(
            due.memory_id,
            tenant_id="tenant-a",
            namespace="assistant",
        )
    assert repo.get(
        future.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    ).version == 1


def test_revision_history_records_create_update_and_tombstone_lineage() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create", content="v1"), now=_now())
    updated = repo.commit(
        _proposal(
            key="update",
            content="v2",
            target=created.memory_id,
            expected_version=created.version,
        ),
        now=_now() + timedelta(seconds=1),
    )
    tombstoned = repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=updated.version,
        now=_now() + timedelta(seconds=2),
    )

    history = repo.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )

    assert [revision.version for revision in history] == [1, 2, 3]
    assert [revision.predecessor_version for revision in history] == [None, 1, 2]
    assert [revision.mutation for revision in history] == [
        "create",
        "update",
        "tombstone",
    ]
    assert [revision.record.content for revision in history] == ["v1", "v2", "v2"]
    assert history[-1].record == tombstoned


def test_projection_outbox_tracks_upserts_and_delete_in_order() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create", content="v1"), now=_now())
    updated = repo.commit(
        _proposal(
            key="update",
            content="v2",
            target=created.memory_id,
            expected_version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )
    repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=updated.version,
        now=_now() + timedelta(seconds=2),
    )

    events = repo.pending_projection_events()

    assert [(event.memory_version, event.action) for event in events] == [
        (1, "upsert"),
        (2, "upsert"),
        (3, "delete"),
    ]
    assert all(event.memory_id == created.memory_id for event in events)
    assert events[0].record.content == "v1"
    assert events[1].record.content == "v2"
    assert events[2].record.state is MemoryState.TOMBSTONED


def test_projection_publish_ack_is_idempotent_and_removes_pending_work() -> None:
    repo = SQLiteMemoryRepository()
    repo.commit(_proposal(key="create"), now=_now())
    event = repo.pending_projection_events()[0]

    first = repo.mark_projection_published(
        event.event_id,
        now=_now() + timedelta(seconds=1),
    )
    second = repo.mark_projection_published(
        event.event_id,
        now=_now() + timedelta(seconds=5),
    )

    assert first.published_at == _now() + timedelta(seconds=1)
    assert second.published_at == first.published_at
    assert repo.pending_projection_events() == ()


def test_projection_publish_unknown_event_fails_closed() -> None:
    repo = SQLiteMemoryRepository()
    with pytest.raises(MemoryNotFound):
        repo.mark_projection_published(
            "missing",
            now=_now(),
        )


def test_idempotent_commit_replay_does_not_duplicate_revision_or_outbox() -> None:
    repo = SQLiteMemoryRepository()
    proposal = _proposal(key="same-key", content="v1")

    first = repo.commit(proposal, now=_now())
    replay = repo.commit(proposal, now=_now() + timedelta(seconds=10))

    assert replay == first
    assert [row.version for row in repo.history(
        first.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )] == [1]
    assert [(row.memory_version, row.action) for row in repo.pending_projection_events()] == [
        (1, "upsert"),
    ]


def test_failed_stale_update_does_not_emit_revision_or_projection_event() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create", content="v1"), now=_now())
    repo.commit(
        _proposal(
            key="update",
            content="v2",
            target=created.memory_id,
            expected_version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )

    with pytest.raises(MemoryConflict):
        repo.commit(
            _proposal(
                key="stale",
                content="stale",
                target=created.memory_id,
                expected_version=1,
            ),
            now=_now() + timedelta(seconds=2),
        )

    assert [row.version for row in repo.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )] == [1, 2]
    assert [(row.memory_version, row.action) for row in repo.pending_projection_events()] == [
        (1, "upsert"),
        (2, "upsert"),
    ]


def test_tombstone_retry_with_original_expected_version_is_idempotent() -> None:
    repo = SQLiteMemoryRepository()
    created = repo.commit(_proposal(key="create"), now=_now())

    first = repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=created.version,
        now=_now() + timedelta(seconds=1),
    )
    retry = repo.tombstone(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=created.version,
        now=_now() + timedelta(seconds=2),
    )

    assert retry == first
    assert [row.version for row in repo.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )] == [1, 2]
    assert [(row.memory_version, row.action) for row in repo.pending_projection_events()] == [
        (1, "upsert"),
        (2, "delete"),
    ]


def test_expiry_records_expire_revision_and_delete_projection() -> None:
    repo = SQLiteMemoryRepository()
    due = repo.commit(
        _proposal(
            key="due-history",
            content="old",
            expires_at=_now() + timedelta(seconds=5),
        ),
        now=_now(),
    )

    expired = repo.expire_due(
        tenant_id="tenant-a",
        namespace="assistant",
        now=_now() + timedelta(seconds=10),
    )

    assert [row.memory_id for row in expired] == [due.memory_id]
    history = repo.history(
        due.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    assert [row.mutation for row in history] == ["create", "expire"]
    events = repo.pending_projection_events()
    assert [(row.memory_version, row.action) for row in events] == [
        (1, "upsert"),
        (2, "delete"),
    ]


def test_revision_and_projection_outbox_survive_repository_restart(tmp_path) -> None:
    path = tmp_path / "memory-authority.sqlite3"
    first = SQLiteMemoryRepository(path)
    created = first.commit(_proposal(key="persist", content="v1"), now=_now())
    updated = first.commit(
        _proposal(
            key="persist-update",
            content="v2",
            target=created.memory_id,
            expected_version=1,
        ),
        now=_now() + timedelta(seconds=1),
    )
    event = first.pending_projection_events()[0]
    first.mark_projection_published(
        event.event_id,
        now=_now() + timedelta(seconds=2),
    )
    first.close()

    reopened = SQLiteMemoryRepository(path)

    history = reopened.history(
        created.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    pending = reopened.pending_projection_events()
    assert [row.version for row in history] == [1, 2]
    assert [row.record.content for row in history] == ["v1", "v2"]
    assert [(row.memory_version, row.action) for row in pending] == [(2, "upsert")]
    assert reopened.get(
        updated.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    ).content == "v2"


@pytest.mark.parametrize("limit", [0, -1])
def test_projection_pending_limit_must_be_positive(limit) -> None:
    repo = SQLiteMemoryRepository()
    with pytest.raises(ValueError):
        repo.pending_projection_events(limit=limit)


@pytest.mark.parametrize("limit", [True, 1.5, "2"])
def test_projection_pending_limit_must_be_integer(limit) -> None:
    repo = SQLiteMemoryRepository()
    with pytest.raises(TypeError):
        repo.pending_projection_events(limit=limit)
