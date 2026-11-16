"""Real Linux memfd seal and source-integrity tests for local weights."""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import sys
import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import ModelIdentity, WeightLoadPlan, WeightShard
from skeleton.ai.model_runtime.sealed_weight_pages import (
    SealedWeightPagesError, open_sealed_weight_pages,
)
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore

linux_sealing = pytest.mark.skipif(
    not sys.platform.startswith("linux") or not hasattr(os, "memfd_create"),
    reason="real Linux memfd required",
)

def _stage(tmp_path: Path, payloads: tuple[bytes, ...]) -> tuple[WeightShardStore, ModelIdentity, str]:
    store = WeightShardStore(tmp_path / "store")
    shards = tuple(
        WeightShard(index, sha256(data).hexdigest(), len(data), "local")
        for index, data in enumerate(payloads)
    )
    identity_digest = sha256(b"weights-model").hexdigest()
    identity = ModelIdentity("sealed-test", "r1", "tiny", identity_digest, identity_digest, identity_digest)
    plan = WeightLoadPlan(identity.identity_digest, shards, sum(len(data) for data in payloads))
    sources = {}
    for index, payload in enumerate(payloads):
        path = tmp_path / ("source_" + str(index))
        path.write_bytes(payload)
        sources[index] = path
    digest = store.stage_plan(identity, plan, sources)
    return store, identity, digest

@linux_sealing
def test_verified_pages_are_read_only_and_source_bound(tmp_path: Path) -> None:
    store, identity, digest = _stage(tmp_path, (b"first weights", b"second weights"))
    with open_sealed_weight_pages(store, digest, model_identity=identity, max_bytes=1024) as pages:
        assert tuple(bytes(page[:]) for page in pages) == (b"first weights", b"second weights")
        with pytest.raises((TypeError, BufferError)):
            pages[0][0] = 1
    assert pages[0].closed
    assert pages[1].closed

@linux_sealing
def test_canonical_store_method_exposes_sealed_pages(tmp_path: Path) -> None:
    store, identity, digest = _stage(tmp_path, (b"sealed bytes",))
    with store.open_sealed_pages(digest, model_identity=identity, max_bytes=64) as pages:
        assert bytes(pages[0][:]) == b"sealed bytes"

@linux_sealing
def test_corrupt_source_never_yields_pages(tmp_path: Path) -> None:
    store, identity, digest = _stage(tmp_path, (b"untampered",))
    target = next((store.root / "objects").glob("*/*"))
    target.write_bytes(b"tampered!!")
    with pytest.raises((SealedWeightPagesError, ValueError)):
        with open_sealed_weight_pages(store, digest, model_identity=identity, max_bytes=64):
            pytest.fail("corrupt weight pages were published")

def test_explicit_budget_blocks_allocation_before_platform_probe(tmp_path: Path) -> None:
    store, identity, digest = _stage(tmp_path, (b"long weights",))
    with pytest.raises(SealedWeightPagesError, match="memory budget"):
        with open_sealed_weight_pages(store, digest, model_identity=identity, max_bytes=1):
            pytest.fail("over-budget pages published")

def test_model_identity_cannot_be_substituted(tmp_path: Path) -> None:
    store, identity, digest = _stage(tmp_path, (b"weights",))
    other = ModelIdentity("other", "r1", "tiny", identity.config_digest, identity.tokenizer_digest, identity.weights_digest)
    with pytest.raises(SealedWeightPagesError, match="identity"):
        with open_sealed_weight_pages(store, digest, model_identity=other, max_bytes=100):
            pytest.fail("wrong identity published")

def test_invalid_memory_budgets_fail_closed(tmp_path: Path) -> None:
    store, identity, digest = _stage(tmp_path, (b"weights",))
    for budget in (0, -1, True, 1 << 63):
        with pytest.raises(SealedWeightPagesError):
            with open_sealed_weight_pages(store, digest, model_identity=identity, max_bytes=budget):
                pytest.fail("invalid budget admitted")


@linux_sealing
def test_progress_checks_refuse_partial_copy_before_publication(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import sealed_weight_pages as owner

    monkeypatch.setattr(owner, "_PROGRESS_QUANTUM", 8)
    monkeypatch.setattr(owner, "_CHUNK", 4)
    store, identity, digest = _stage(tmp_path, (b"a" * 12, b"b" * 8))
    checks = []
    created = []
    original = owner.os.memfd_create

    def capture(*args, **kwargs):
        fd = original(*args, **kwargs)
        created.append(fd)
        return fd

    def check(copied, total):
        checks.append((copied, total))
        if copied:
            raise RuntimeError("pressure became critical")

    monkeypatch.setattr(owner.os, "memfd_create", capture)
    with pytest.raises(RuntimeError, match="pressure"):
        with store.open_sealed_pages(digest, model_identity=identity, max_bytes=32,
                                     progress_check=check):
            pytest.fail("incomplete copy published")
    assert checks == [(0, 20), (8, 20)]
    assert created
    for fd in created:
        with pytest.raises(OSError):
            os.fstat(fd)


@linux_sealing
def test_progress_covers_all_shards_and_final_exact_bytes(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import sealed_weight_pages as owner
    monkeypatch.setattr(owner, "_PROGRESS_QUANTUM", 8)
    monkeypatch.setattr(owner, "_CHUNK", 4)
    store, identity, digest = _stage(tmp_path, (b"a" * 12, b"b" * 8))
    checks = []
    with store.open_sealed_pages(digest, model_identity=identity, max_bytes=32,
                                 progress_check=lambda copied, total: checks.append((copied, total))) as pages:
        assert tuple(bytes(page) for page in pages) == (b"a" * 12, b"b" * 8)
        assert checks == [(0, 20), (8, 20), (16, 20), (20, 20)]


@linux_sealing
def test_outstanding_memoryview_does_not_skip_other_page_cleanup(tmp_path):
    store, identity, digest = _stage(tmp_path, (b"first", b"second"))
    view = None
    try:
        with pytest.raises(SealedWeightPagesError, match="cleanup remains incomplete"):
            with store.open_sealed_pages(digest, model_identity=identity, max_bytes=32) as pages:
                view = memoryview(pages[1])
        assert pages[0].closed
        assert not pages[1].closed
        assert bytes(view) == b"second"
    finally:
        if view is not None:
            view.release()
            pages[1].close()


def test_mapping_ceiling_refuses_before_platform_probe(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import sealed_weight_pages as owner
    store, identity, key = _stage(tmp_path, (b"a", b"b"))
    monkeypatch.setattr(owner, "_require_sealing", lambda: pytest.fail("allocation before mapping admission"))
    with pytest.raises(SealedWeightPagesError, match="mapping ceiling"):
        with store.open_sealed_pages(key, model_identity=identity, max_bytes=8, max_mappings=1):
            pytest.fail("over-limit mapping published")


@linux_sealing
def test_sealed_loader_owns_only_one_source_descriptor_and_copies_once(tmp_path, monkeypatch):
    from contextlib import contextmanager
    store, identity, key = _stage(tmp_path, (b"alpha", b"beta", b"gamma"))
    original = store._object_reader
    opened = []
    active = 0

    @contextmanager
    def observe(shard):
        nonlocal active
        active += 1
        opened.append(shard.index)
        try:
            assert active == 1
            with original(shard) as stream:
                yield stream
        finally:
            active -= 1

    monkeypatch.setattr(store, "_object_reader", observe)
    monkeypatch.setattr(store, "open_verified",
                        lambda *args, **kwargs: pytest.fail("eager source prehash invoked"))
    with store.open_sealed_pages(key, model_identity=identity, max_bytes=32) as pages:
        assert opened == [0, 1, 2] and active == 0
        assert tuple(bytes(page) for page in pages) == (b"alpha", b"beta", b"gamma")


@linux_sealing
def test_manifest_pin_rejects_mutation_before_sealed_publication(tmp_path):
    import json
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    store, identity, key = _stage(tmp_path, (b"one", b"two"))
    _, pin, _ = store.manifest_evidence(key)
    manifest = store.manifests / (key + ".json")

    def checkpoint(copied, total):
        if copied == total:
            record = json.loads(manifest.read_bytes())
            record["weights_digest"] = "0" * 64
            manifest.write_bytes(canonical_bytes(record))

    with pytest.raises(SealedWeightPagesError, match="manifest identity changed"):
        with store.open_sealed_pages(key, model_identity=identity, max_bytes=32,
                                     expected_manifest_sha256=pin, progress_check=checkpoint):
            pytest.fail("changed manifest published")


def test_independent_manifest_pin_refuses_before_native_platform_probe(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import sealed_weight_pages as owner
    store, identity, key = _stage(tmp_path, (b"payload",))
    monkeypatch.setattr(owner, "_require_sealing", lambda: pytest.fail("unverified manifest reached native owner"))
    with pytest.raises(SealedWeightPagesError, match="manifest identity unavailable"):
        with store.open_sealed_pages(key, model_identity=identity, max_bytes=64,
                                     expected_manifest_sha256="0" * 64):
            pytest.fail("wrong manifest pin accepted")
