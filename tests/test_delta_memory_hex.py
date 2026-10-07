"""Δ-Memory memory-hex wiring + concurrency (Pack J, round 2)."""

from __future__ import annotations

import random
import threading
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

import skeleton.memory as memory_pkg
from skeleton.contracts.memory_record import (
    MemoryKind,
    MemoryState,
    MemoryWriteProposal,
    memory_payload_digest,
)
from skeleton.memory.delta_memory import (
    DeltaMemory,
    DeltaMemoryPort,
    JsonFileDeltaSnapshotStore,
    PersistingDeltaMemory,
    create_delta_memory,
    delta_memory_adapters,
    register_delta_memory_adapter,
)
from skeleton.memory.delta_projection import DeltaMemoryProjection, delta_entry
from skeleton.memory.projection import MemoryProjectionCoordinator, ProjectionState
from skeleton.persistence.memory_repository import SQLiteMemoryRepository


def _now():
    return datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)


def _proposal(*, key, content, target=None, version=None):
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


def _evolve(record, **changes):
    """dataclasses.replace that keeps payload_digest consistent with content."""
    content = changes.get("content", record.content)
    content_ref = changes.get("content_ref", record.content_ref)
    changes["payload_digest"] = memory_payload_digest(
        kind=record.kind, content=content, content_ref=content_ref,
        provenance_refs=record.provenance_refs,
    )
    return replace(record, **changes)


# -- port + registry ---------------------------------------------------------


def test_package_exports_hex_surface():
    assert memory_pkg.DeltaMemory is DeltaMemory
    assert memory_pkg.DeltaMemoryPort is DeltaMemoryPort
    assert memory_pkg.create_delta_memory is create_delta_memory


def test_builtin_adapters_satisfy_port(tmp_path):
    assert {"memory", "json_file", "in_memory_persisting"} <= set(delta_memory_adapters())
    plain = create_delta_memory(window_cap=4)
    assert isinstance(plain, DeltaMemory) and isinstance(plain, DeltaMemoryPort)
    filed = create_delta_memory("json_file", path=tmp_path / "d.json", window_cap=2,
                                strict=True, json_values=True)
    assert isinstance(filed, PersistingDeltaMemory) and isinstance(filed, DeltaMemoryPort)
    filed.write("a", 1)
    filed.write("b", 2)
    assert JsonFileDeltaSnapshotStore(tmp_path / "d.json").load_snapshot() == {"a": 1, "b": 2}
    assert isinstance(create_delta_memory("in_memory_persisting"), DeltaMemoryPort)


def test_registry_is_extend_only_and_validates_results():
    name = f"test-{uuid4().hex[:8]}"
    register_delta_memory_adapter(name, lambda **kw: DeltaMemory(**kw))
    assert isinstance(create_delta_memory(name, window_cap=3), DeltaMemory)
    with pytest.raises(ValueError):
        register_delta_memory_adapter(name, DeltaMemory)
    with pytest.raises(ValueError):
        register_delta_memory_adapter("memory", DeltaMemory)  # builtins protected
    register_delta_memory_adapter(name, lambda **kw: object(), replace=True)
    with pytest.raises(TypeError):
        create_delta_memory(name)
    with pytest.raises(KeyError):
        create_delta_memory("nope-" + name)
    with pytest.raises(ValueError):
        register_delta_memory_adapter("  ", DeltaMemory)
    with pytest.raises(TypeError):
        register_delta_memory_adapter(name + "x", "not callable")


# -- projection adapter ------------------------------------------------------


def test_projection_syncs_from_canonical_authority_via_coordinator():
    repo = SQLiteMemoryRepository()
    one = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    repo.commit(_proposal(key="two", content="beta"), now=_now())
    dm = DeltaMemory(window_cap=4, json_values=True)
    projection = DeltaMemoryProjection("delta", dm)
    report = MemoryProjectionCoordinator(repo).sync_subject(
        tenant_id="tenant-a", namespace="assistant", subject_id="user-a",
        projections=[projection],
    )
    assert [r.state for r in report.results] == [ProjectionState.HEALTHY]
    assert len(dm.materialize()) == 2
    entry = projection.entry(one.memory_id)
    assert entry["content"] == "alpha" and entry["version"] == 1
    assert entry["canonical_memory_id"] == one.memory_id


def test_version_guard_rejects_stale_and_replayed_upserts():
    repo = SQLiteMemoryRepository()
    v1 = repo.commit(_proposal(key="k", content="old"), now=_now())
    v2 = _evolve(v1, version=2, content="new")
    projection = DeltaMemoryProjection("delta", DeltaMemory(window_cap=2))
    projection.upsert(v2)
    projection.upsert(v1)  # out-of-order older dispatch
    projection.upsert(v2)  # replay
    assert projection.entry(v1.memory_id)["content"] == "new"
    assert projection.stale_skips == 2 and projection.upserts == 1


def test_non_active_record_tombstones_entry_and_allows_resurrection():
    repo = SQLiteMemoryRepository()
    rec = repo.commit(_proposal(key="k", content="x"), now=_now())
    projection = DeltaMemoryProjection("delta", DeltaMemory(window_cap=8))
    projection.upsert(rec)
    projection.upsert(_evolve(rec, version=2, state=MemoryState.TOMBSTONED))
    assert projection.entry(rec.memory_id) is None
    projection.upsert(_evolve(rec, version=3, content="back"))
    assert projection.entry(rec.memory_id)["content"] == "back"


def test_content_ref_records_project_as_refs():
    repo = SQLiteMemoryRepository()
    rec = repo.commit(_proposal(key="k", content="x"), now=_now())
    ref = _evolve(rec, content=None, content_ref="blob://abc")
    entry = delta_entry(ref)
    assert entry["content"] is None and entry["content_ref"] == "blob://abc"


def test_projection_rejects_bad_wiring():
    with pytest.raises(ValueError):
        DeltaMemoryProjection(" ", DeltaMemory())
    with pytest.raises(TypeError):
        DeltaMemoryProjection("x", object())


def test_projection_over_persisting_store_survives_restart(tmp_path):
    repo = SQLiteMemoryRepository()
    rec = repo.commit(_proposal(key="k", content="persist"), now=_now())
    path = tmp_path / "proj.json"
    first = DeltaMemoryProjection(
        "delta", create_delta_memory("json_file", path=path, window_cap=8, strict=True)
    )
    first.upsert(rec)
    first.memory.flush()
    second = DeltaMemoryProjection(
        "delta", create_delta_memory("json_file", path=path, window_cap=8, strict=True)
    )
    assert second.entry(rec.memory_id)["content"] == "persist"
    second.upsert(rec)  # same version after restart -> skipped
    assert second.stale_skips == 1


# -- concurrency -------------------------------------------------------------


def test_concurrent_mixed_ops_match_serial_per_key_model():
    """Each thread owns disjoint keys; final state must equal its own serial model."""
    dm = DeltaMemory(window_cap=7)
    models = {}

    def worker(tid):
        rng = random.Random(tid)
        model = {}
        for i in range(400):
            key = f"t{tid}:k{rng.randrange(12)}"
            op = rng.random()
            if op < 0.6:
                dm.write(key, i)
                model[key] = i
            elif op < 0.8:
                dm.delete(key)
                model.pop(key, None)
            else:
                assert dm.get(key, "absent") == model.get(key, "absent")
        models[tid] = model

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    expected = {}
    for m in models.values():
        expected.update(m)
    assert dm.materialize() == expected
    assert dm.stats()["window_len"] < 7


def test_readers_never_observe_torn_state_during_compaction():
    dm = DeltaMemory(window_cap=5)
    stop = threading.Event()
    failures = []

    def writer():
        for i in range(3000):
            dm.write("counter", i)
        stop.set()

    def reader():
        last = -1
        while not stop.is_set():
            found, v = dm.lookup("counter")
            if found:
                if v < last:
                    failures.append((last, v))
                last = v
            st = dm.stats()
            if st["window_len"] >= 5:
                failures.append(("window", st["window_len"]))

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not failures
    assert dm.read("counter") == 2999


def test_concurrent_persisting_writes_flush_a_complete_snapshot(tmp_path):
    path = tmp_path / "c.json"
    pdm = create_delta_memory("json_file", path=path, window_cap=9, fsync=False)

    def worker(tid):
        for i in range(150):
            pdm.write(f"t{tid}:{i % 10}", i)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    pdm.flush()
    snap = JsonFileDeltaSnapshotStore(path).load_snapshot()
    assert snap == pdm.materialize()
    assert len(snap) == 60 and all(snap[f"t{t}:{k}"] == 140 + k for t in range(6) for k in range(10))


def test_concurrent_projection_upserts_keep_highest_version():
    repo = SQLiteMemoryRepository()
    base = repo.commit(_proposal(key="k", content="v1"), now=_now())
    projection = DeltaMemoryProjection("delta", DeltaMemory(window_cap=3))
    versions = list(range(1, 201))
    random.Random(7).shuffle(versions)
    chunks = [versions[i::8] for i in range(8)]

    def worker(vs):
        for v in vs:
            projection.upsert(_evolve(base, version=v, content=f"v{v}"))

    threads = [threading.Thread(target=worker, args=(c,)) for c in chunks]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert projection.entry(base.memory_id)["version"] == 200
    assert projection.upserts + projection.stale_skips == 200
