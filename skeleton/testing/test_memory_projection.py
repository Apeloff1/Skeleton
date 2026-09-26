from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from skeleton.contracts.memory_record import (
    MemoryKind,
    MemoryWriteProposal,
    memory_payload_digest,
)
from skeleton.memory.core import CAGStore, InMemoryTFIDFStore, MAGStore
from skeleton.intelligence.admission import ResourceBudget
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.memory.projection import (
    CAGStoreProjection,
    LegacyMemoryStoreProjection,
    MAGStoreProjection,
    MemoryProjectionCoordinator,
    ProjectionAdmissionError,
    ProjectionState,
    TFIDFStoreProjection,
    VectorStoreProjection,
)
from skeleton.memory.vector import VectorStore
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk, MemoryQueryResult
from skeleton.persistence.memory_repository import SQLiteMemoryRepository


class FakeStore(MemoryStore):
    def __init__(self, *, fail_add: bool = False) -> None:
        self.items: dict[str, MemoryChunk] = {}
        self.fail_add = fail_add

    def add(self, chunk: MemoryChunk) -> None:
        if self.fail_add:
            raise RuntimeError("projection unavailable")
        self.items[chunk.id] = chunk

    def query(self, query_text, *, top_k=5, metadata_filter=None, min_score=0.0):
        return [
            MemoryQueryResult(chunk=item, score=1.0, rank=index + 1)
            for index, item in enumerate(self.items.values())
        ][:top_k]

    def delete(self, chunk_id: str) -> bool:
        return self.items.pop(chunk_id, None) is not None

    def health(self):
        return {"ok": not self.fail_add}


def _now():
    return datetime(2026, 9, 23, 17, 15, tzinfo=timezone.utc)


def _proposal(*, key: str, content: str, target=None, version=None):
    return MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        kind=MemoryKind.SEMANTIC,
        idempotency_key=key,
        proposed_at=_now(),
        content=content,
        provenance_refs=("conversation:1",),
        source_operation_id=str(uuid4()),
        target_memory_id=target,
        expected_version=version,
    )


def test_projection_is_rebuildable_from_canonical_authority() -> None:
    repo = SQLiteMemoryRepository()
    one = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    two = repo.commit(_proposal(key="two", content="beta"), now=_now())
    store = FakeStore()
    projection = LegacyMemoryStoreProjection("rag", store)
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
        known_projection_ids=("stale-id",),
    )

    assert report.degraded is False
    assert set(store.items) == {one.memory_id, two.memory_id}
    assert store.items[one.memory_id].metadata["canonical_memory_id"] == one.memory_id
    assert store.items[one.memory_id].source_tier == "derived:rag"


def test_tombstone_deletes_projection_without_erasing_canonical_lineage() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    store = FakeStore()
    projection = LegacyMemoryStoreProjection("rag", store)
    coordinator = MemoryProjectionCoordinator(repo)
    coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )
    assert record.memory_id in store.items

    tombstone = repo.tombstone(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now(),
    )
    report = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )

    assert tombstone.memory_id not in store.items
    assert report.tombstones == 1
    exported = coordinator.export_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    )
    assert exported[0]["state"] == "tombstoned"
    assert exported[0]["payload_digest"] == record.payload_digest


def test_projection_failure_is_degraded_not_authoritative_rollback() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    healthy_store = FakeStore()
    failing_store = FakeStore(fail_add=True)
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(
            LegacyMemoryStoreProjection("rag", healthy_store),
            LegacyMemoryStoreProjection("mag", failing_store),
        ),
    )

    assert report.degraded is True
    assert report.results[0].state is ProjectionState.HEALTHY
    assert report.results[1].state is ProjectionState.DEGRADED
    assert report.results[1].error_code == "RuntimeError"
    assert record.memory_id in healthy_store.items
    canonical = repo.get(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    assert canonical.payload_digest == record.payload_digest


def test_export_ignores_projection_health_entirely() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    coordinator = MemoryProjectionCoordinator(repo)

    exported = coordinator.export_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    )

    assert exported == (record.as_dict(),)

def test_real_tfidf_and_vector_stores_rebuild_from_canonical_authority() -> None:
    repo = SQLiteMemoryRepository()
    one = repo.commit(_proposal(key="one-real", content="alpha memory"), now=_now())
    two = repo.commit(_proposal(key="two-real", content="beta memory"), now=_now())
    tfidf = InMemoryTFIDFStore()
    vector = VectorStore(dims=32)
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(
            TFIDFStoreProjection("tfidf", tfidf),
            VectorStoreProjection("vector", vector),
        ),
        known_projection_ids=("stale-memory",),
    )

    assert report.degraded is False
    assert tfidf.stats()["documents"] == 2
    assert vector.stats()["documents"] == 2
    assert {result.chunk.chunk_id for result in tfidf.query("alpha", top_k=5)} == {one.memory_id}
    assert vector.query("beta", top_k=5)[0].chunk.chunk_id in {one.memory_id, two.memory_id}


def test_real_cag_and_mag_stores_delete_tombstoned_memory() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="real-derived", content="remember real"), now=_now())
    cag = CAGStore()
    mag = MAGStore(agent_id="user-a")
    coordinator = MemoryProjectionCoordinator(repo)
    projections = (
        CAGStoreProjection("cag", cag),
        MAGStoreProjection("mag", mag),
    )

    initial = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=projections,
    )
    assert initial.degraded is False
    assert cag.recall(record.memory_id)["text"] == "remember real"
    assert mag.stats()["episodes"] == 1

    repo.tombstone(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now(),
    )
    after = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=projections,
    )

    assert after.tombstones == 1
    assert cag.recall(record.memory_id) is None
    assert mag.stats()["episodes"] == 0


def test_real_tfidf_upsert_replaces_prior_terms_without_counter_drift() -> None:
    repo = SQLiteMemoryRepository()
    first = repo.commit(_proposal(key="tf-one", content="alpha alpha"), now=_now())
    store = InMemoryTFIDFStore()
    projection = TFIDFStoreProjection("tfidf", store)
    coordinator = MemoryProjectionCoordinator(repo)

    coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )
    assert store.stats()["documents"] == 1

    repo.commit(
        _proposal(
            key="tf-two",
            content="beta beta",
            target=first.memory_id,
            version=1,
        ),
        now=_now(),
    )
    coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )

    assert store.stats()["documents"] == 1
    assert store.query("alpha", top_k=5) == []
    assert store.query("beta", top_k=5)[0].chunk.chunk_id == first.memory_id


def test_outbox_dispatch_applies_versions_in_order_and_acks() -> None:
    repo = SQLiteMemoryRepository()
    first = repo.commit(
        _proposal(key="dispatch-create", content="alpha"),
        now=_now(),
    )
    repo.commit(
        _proposal(
            key="dispatch-update",
            content="beta",
            target=first.memory_id,
            version=1,
        ),
        now=_now(),
    )
    store = FakeStore()
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.dispatch_pending(
        projections=(LegacyMemoryStoreProjection("rag", store),),
        limit=10,
        now=_now(),
    )

    assert report.degraded is False
    assert report.attempted_events == 2
    assert report.published_events == 2
    assert report.blocked_event_id is None
    assert report.remaining_pending_sample == 0
    assert [attempt.memory_version for attempt in report.attempts] == [1, 2]
    assert all(attempt.published for attempt in report.attempts)
    assert store.items[first.memory_id].text == "beta"
    assert store.items[first.memory_id].metadata["canonical_version"] == 2
    assert repo.pending_projection_events() == ()


def test_outbox_failure_blocks_later_versions_until_retry() -> None:
    repo = SQLiteMemoryRepository()
    first = repo.commit(
        _proposal(key="dispatch-fail-create", content="v1"),
        now=_now(),
    )
    repo.commit(
        _proposal(
            key="dispatch-fail-update",
            content="v2",
            target=first.memory_id,
            version=1,
        ),
        now=_now(),
    )
    healthy = FakeStore()
    failing = FakeStore(fail_add=True)
    coordinator = MemoryProjectionCoordinator(repo)
    projections = (
        LegacyMemoryStoreProjection("healthy", healthy),
        LegacyMemoryStoreProjection("failing", failing),
    )

    blocked = coordinator.dispatch_pending(
        projections=projections,
        limit=10,
        now=_now(),
    )

    assert blocked.degraded is True
    assert blocked.attempted_events == 2
    assert blocked.published_events == 1
    assert blocked.blocked_event_id is not None
    assert blocked.attempts[0].memory_version == 1
    assert blocked.attempts[0].published is True
    assert blocked.attempts[0].superseded is True
    assert blocked.attempts[1].memory_version == 2
    assert blocked.attempts[1].published is False
    assert len(repo.pending_projection_event_headers()) == 1
    assert healthy.items[first.memory_id].text == "v2"

    failing.fail_add = False
    recovered = coordinator.dispatch_pending(
        projections=projections,
        limit=10,
        now=_now(),
    )

    assert recovered.degraded is False
    assert recovered.published_events == 1
    assert repo.pending_projection_events() == ()
    assert healthy.items[first.memory_id].text == "v2"
    assert failing.items[first.memory_id].text == "v2"


def test_outbox_tombstone_removes_derived_memory() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(
        _proposal(key="dispatch-delete", content="temporary"),
        now=_now(),
    )
    store = FakeStore()
    projection = LegacyMemoryStoreProjection("rag", store)
    coordinator = MemoryProjectionCoordinator(repo)

    initial = coordinator.dispatch_pending(
        projections=(projection,),
        now=_now(),
    )
    assert initial.published_events == 1
    assert record.memory_id in store.items

    repo.tombstone(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now(),
    )
    deleted = coordinator.dispatch_pending(
        projections=(projection,),
        now=_now(),
    )

    assert deleted.published_events == 1
    assert deleted.attempts[0].action == "delete"
    assert record.memory_id not in store.items
    assert repo.pending_projection_events() == ()


def test_outbox_dispatch_requires_nonempty_unique_projection_names() -> None:
    repo = SQLiteMemoryRepository()
    repo.commit(_proposal(key="dispatch-validation", content="x"), now=_now())
    coordinator = MemoryProjectionCoordinator(repo)

    import pytest

    with pytest.raises(ValueError, match="at least one projection"):
        coordinator.dispatch_pending(projections=())

    one = LegacyMemoryStoreProjection("duplicate", FakeStore())
    two = LegacyMemoryStoreProjection("duplicate", FakeStore())
    with pytest.raises(ValueError, match="unique"):
        coordinator.dispatch_pending(projections=(one, two))


def test_outbox_dispatch_limit_preserves_pending_tail() -> None:
    repo = SQLiteMemoryRepository()
    repo.commit(_proposal(key="dispatch-limit-one", content="one"), now=_now())
    repo.commit(_proposal(key="dispatch-limit-two", content="two"), now=_now())
    store = FakeStore()
    coordinator = MemoryProjectionCoordinator(repo)

    first = coordinator.dispatch_pending(
        projections=(LegacyMemoryStoreProjection("rag", store),),
        limit=1,
        now=_now(),
    )

    assert first.published_events == 1
    assert first.remaining_pending_sample == 1
    assert len(repo.pending_projection_event_headers()) == 1


def test_stale_pending_event_cannot_regress_rebuilt_projection() -> None:
    repo = SQLiteMemoryRepository()
    first = repo.commit(
        _proposal(key="stale-fence-create", content="v1"),
        now=_now(),
    )
    repo.commit(
        _proposal(
            key="stale-fence-update",
            content="v2",
            target=first.memory_id,
            version=1,
        ),
        now=_now(),
    )
    store = FakeStore()
    projection = LegacyMemoryStoreProjection("rag", store)
    coordinator = MemoryProjectionCoordinator(repo)

    rebuilt = coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )
    assert rebuilt.degraded is False
    assert store.items[first.memory_id].text == "v2"

    bounded = coordinator.dispatch_pending(
        projections=(projection,),
        limit=1,
        now=_now(),
    )

    assert bounded.published_events == 1
    assert bounded.attempts[0].memory_version == 1
    assert bounded.attempts[0].superseded is True
    assert store.items[first.memory_id].text == "v2"
    assert [(event.memory_version, event.action) for event in repo.pending_projection_events()] == [
        (2, "upsert"),
    ]


def test_current_projection_event_must_match_canonical_record() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(
        _proposal(key="canonical-fence", content="canonical"),
        now=_now(),
    )
    # Corrupt only the durable outbox snapshot while keeping that snapshot
    # internally self-consistent. The canonical fence must reject divergence
    # from authority rather than relying on MemoryRecord validation to catch it.
    with repo._lock:
        row = repo._connection.execute(
            """
            SELECT record_json
            FROM canonical_memory_projection_outbox
            WHERE repository_namespace = ? AND memory_id = ?
            """,
            (repo.repository_namespace, record.memory_id),
        ).fetchone()
        assert row is not None
        snapshot = json.loads(row["record_json"])
        snapshot["content"] = "tampered"
        snapshot["payload_digest"] = memory_payload_digest(
            kind=snapshot["kind"],
            content=snapshot["content"],
            content_ref=snapshot.get("content_ref"),
            provenance_refs=tuple(snapshot.get("provenance_refs") or ()),
        )
        repo._connection.execute(
            """
            UPDATE canonical_memory_projection_outbox
            SET record_json = ?
            WHERE repository_namespace = ? AND memory_id = ?
            """,
            (
                json.dumps(
                    snapshot,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                repo.repository_namespace,
                record.memory_id,
            ),
        )

    report = MemoryProjectionCoordinator(repo).dispatch_pending(
        projections=(LegacyMemoryStoreProjection("rag", FakeStore()),),
        now=_now(),
    )

    assert report.degraded is True
    assert report.published_events == 0
    assert report.blocked_event_id is not None
    assert report.attempts[0].results[0].projection == "canonical-fence"
    assert len(repo.pending_projection_events()) == 1

def test_material_projection_rebuild_is_admitted_and_reconciled() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(
        _proposal(
            key="admitted-rebuild",
            content="material canonical memory " * 16,
        ),
        now=_now(),
    )
    store = FakeStore()
    runtime = AdmissionRuntime()
    coordinator = MemoryProjectionCoordinator(
        repo,
        admission_runtime=runtime,
        rebuild_budget=ResourceBudget(max_storage_bytes=1024 * 1024),
    )

    report = coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(LegacyMemoryStoreProjection("rag", store),),
        admission_operation_id="retrieval-rebuild-1",
    )

    assert report.degraded is False
    assert record.memory_id in store.items
    assert runtime.snapshot()["active_operations"] == ()
    telemetry = runtime.telemetry_snapshot()["metrics"]
    assert telemetry["counters"]["admission.admitted_total"] == 1
    assert telemetry["counters"]["admission.completed_total"] == 1
    actual = telemetry["samples"]["admission.actual.storage_bytes"]
    assert len(actual) == 1
    assert actual[0] > 0


def test_projection_rebuild_denial_happens_before_derived_mutation() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(
        _proposal(
            key="denied-rebuild",
            content="large canonical memory " * 32,
        ),
        now=_now(),
    )
    store = FakeStore()
    store.add(
        MemoryChunk(
            id="stale-id",
            text="stale projection",
            metadata={},
            source_tier="derived:rag",
        )
    )
    runtime = AdmissionRuntime()
    coordinator = MemoryProjectionCoordinator(
        repo,
        admission_runtime=runtime,
        rebuild_budget=ResourceBudget(max_storage_bytes=1),
    )

    with pytest.raises(
        ProjectionAdmissionError,
        match="denied by resource admission",
    ):
        coordinator.rebuild_subject(
            tenant_id="tenant-a",
            namespace="assistant",
            subject_id="user-a",
            projections=(LegacyMemoryStoreProjection("rag", store),),
            known_projection_ids=("stale-id",),
            admission_operation_id="retrieval-rebuild-denied",
        )

    assert "stale-id" in store.items
    assert record.memory_id not in store.items
    assert runtime.snapshot()["active_operations"] == ()


def test_admitted_projection_rebuild_requires_operation_identity() -> None:
    repo = SQLiteMemoryRepository()
    repo.commit(
        _proposal(key="missing-rebuild-id", content="canonical"),
        now=_now(),
    )
    store = FakeStore()
    coordinator = MemoryProjectionCoordinator(
        repo,
        admission_runtime=AdmissionRuntime(),
    )

    with pytest.raises(
        ProjectionAdmissionError,
        match="requires operation_id",
    ):
        coordinator.rebuild_subject(
            tenant_id="tenant-a",
            namespace="assistant",
            subject_id="user-a",
            projections=(LegacyMemoryStoreProjection("rag", store),),
        )

    assert store.items == {}
