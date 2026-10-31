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
