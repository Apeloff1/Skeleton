"""Physical chunk-index and restartable range campaign tests on real local files."""
from __future__ import annotations

from hashlib import sha256
import io
import json
import os

import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore, WeightShardStoreError
from skeleton.ai.model_runtime.weight_store_disk_owner import DiskAdmissionPolicy, WeightStoreDiskOwner
from skeleton.ai.model_runtime.weight_store_range import (
    WeightChunkIndex, advance_weight_range, build_weight_chunk_index,
    check_completed_weight_range, read_chunk_index, start_weight_range, weight_range_status,
)
from skeleton.testing.test_weight_store_disk_owner import prepare

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX managed storage required")
CHUNK = 64 * 1024


def setup(tmp_path):
    owner = WeightStoreDiskOwner(WeightShardStore(tmp_path / "store"),
                                DiskAdmissionPolicy(16 * CHUNK, minimum_free_bytes=0))
    data = b"a" * CHUNK + b"b" * CHUNK + b"last seven"
    identity, plan, paths = prepare(tmp_path, data)
    owner.stage(identity, plan, paths)
    record = build_weight_chunk_index(
        owner, object_digest=plan.shards[0].digest,
        object_bytes=len(data), maximum_bytes=len(data), chunk_bytes=CHUNK,
    )
    index = read_chunk_index(io.BytesIO(canonical_bytes(record) + b"\n"),
                             expected_digest=record["digest"])
    return owner, plan, data, index


def step(owner, index, state, *, maximum_bytes=CHUNK, maximum_chunks=1):
    return advance_weight_range(owner, index, expected_index_digest=index.digest,
                                campaign_digest=state["digest"],
                                maximum_chunks=maximum_chunks, maximum_bytes=maximum_bytes)


def test_index_is_deterministic_and_preserves_raw_digest_and_tail(tmp_path):
    owner, plan, data, index = setup(tmp_path)
    assert index.object_digest == sha256(data).hexdigest() == plan.shards[0].digest
    assert index.chunk_sha256 == tuple(sha256(data[i:i + CHUNK]).hexdigest()
                                       for i in range(0, len(data), CHUNK))
    assert index.size_at(2) == len(b"last seven")
    assert index.prefix_bytes(3) == len(data)
    again = build_weight_chunk_index(owner, object_digest=index.object_digest,
                                     object_bytes=len(data), maximum_bytes=len(data),
                                     chunk_bytes=CHUNK)
    assert again == index.record()


def test_resume_reads_only_requested_chunk_ranges_and_rejects_stale_cursor(tmp_path, monkeypatch):
    owner, _, data, index = setup(tmp_path)
    state = start_weight_range(owner, index, expected_index_digest=index.digest)
    from skeleton.ai.model_runtime import weight_store_range as module
    original = module._read_range
    calls = []

    def observed(stream, size, whole=None):
        calls.append((stream.tell(), size))
        return original(stream, size, whole)

    monkeypatch.setattr(module, "_read_range", observed)
    one = step(owner, index, state)
    assert one["campaign"]["verified_chunks"] == 1
    assert one["bytes_this_tranche"] == CHUNK
    reopened = WeightStoreDiskOwner.open_existing(WeightShardStore(owner._store.root, create=False))
    assert weight_range_status(reopened)["campaign"] == one["campaign"]
    with pytest.raises(WeightShardStoreError, match="exact active range"):
        step(reopened, index, state)
    two = step(reopened, index, one["campaign"])
    three = step(reopened, index, two["campaign"])
    assert three["status"] == "completed"
    assert three["campaign"]["verified_bytes"] == len(data)
    assert calls == [(0, CHUNK), (CHUNK, CHUNK), (2 * CHUNK, len(data) - 2 * CHUNK)]
    observation = check_completed_weight_range(
        reopened, index, expected_index_digest=index.digest,
        campaign_digest=three["campaign"]["digest"],
    )
    assert observation["current_metadata_revalidated"]
    assert not observation["current_bytes_revalidated"]
    assert not observation["raw_sha256_recomputed"]
    assert not observation["runtime_scrub_substitute"]


def test_small_tranche_does_not_advance_or_read_bytes(tmp_path, monkeypatch):
    owner, _, _, index = setup(tmp_path)
    state = start_weight_range(owner, index, expected_index_digest=index.digest)
    from skeleton.ai.model_runtime import weight_store_range as module
    monkeypatch.setattr(module, "_read_range", lambda *a, **k: pytest.fail("read without budget"))
    result = step(owner, index, state, maximum_bytes=CHUNK - 1)
    assert result["status"] == "larger_tranche_required"
    assert result["required_bytes"] == CHUNK and result["campaign"] == state
    assert weight_range_status(owner)["campaign"] == state


def test_corruption_before_campaign_start_is_detected_by_original_chunk_index(tmp_path):
    owner, plan, data, index = setup(tmp_path)
    path = owner._store.objects / index.object_digest[:2] / index.object_digest
    path.write_bytes(data[:CHUNK] + b"x" * CHUNK + data[2 * CHUNK:])
    # New metadata is captured at campaign start, but content is still pinned
    # to the independently retained index of the original verified object.
    state = start_weight_range(owner, index, expected_index_digest=index.digest)
    result = step(owner, index, state, maximum_bytes=2 * CHUNK, maximum_chunks=2)
    assert result["status"] == "blocked"
    assert result["failure"] == {"reason": "chunk_content_mismatch", "chunk": 1}
    assert result["campaign"]["verified_chunks"] == 0
    assert weight_range_status(owner)["campaign"]["failure"] == result["failure"]
    with pytest.raises(WeightShardStoreError, match="whole-object digest mismatch"):
        build_weight_chunk_index(owner, object_digest=index.object_digest,
                                 object_bytes=index.object_bytes, maximum_bytes=index.object_bytes,
                                 chunk_bytes=CHUNK)
    assert path.read_bytes() != data and plan.shards[0].digest == index.object_digest


def test_same_size_mutation_between_tranches_blocks_progress(tmp_path):
    owner, _, data, index = setup(tmp_path)
    state = start_weight_range(owner, index, expected_index_digest=index.digest)
    first = step(owner, index, state)
    path = owner._store.objects / index.object_digest[:2] / index.object_digest
    path.write_bytes(b"x" + data[1:])
    result = step(owner, index, first["campaign"])
    assert result["status"] == "blocked"
    assert result["failure"]["reason"] == "object_identity_changed"
    assert result["campaign"]["verified_chunks"] == 1


def test_interrupted_read_preserves_exact_prior_cursor(tmp_path, monkeypatch):
    owner, _, _, index = setup(tmp_path)
    state = start_weight_range(owner, index, expected_index_digest=index.digest)
    from skeleton.ai.model_runtime import weight_store_range as module
    original = module._read_range
    calls = []

    def interrupt(stream, size, whole=None):
        calls.append(size)
        if len(calls) == 2:
            raise KeyboardInterrupt("interrupted")
        return original(stream, size, whole)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_read_range", interrupt)
        with pytest.raises(KeyboardInterrupt):
            step(owner, index, state, maximum_bytes=2 * CHUNK, maximum_chunks=2)
    assert weight_range_status(owner)["campaign"] == state
    result = step(owner, index, state, maximum_bytes=index.object_bytes, maximum_chunks=3)
    assert result["status"] == "completed"
    assert result["campaign"]["verified_bytes"] == index.object_bytes


def test_independent_pin_and_canonical_index_validation(tmp_path):
    _, _, _, index = setup(tmp_path)
    raw = canonical_bytes(index.record())
    with pytest.raises(WeightShardStoreError, match="pinned chunk index"):
        read_chunk_index(io.BytesIO(raw), expected_digest="0" * 64)
    altered = index.record()
    altered["chunk_sha256"][0] = "0" * 64
    with pytest.raises(WeightShardStoreError, match="pinned chunk index"):
        read_chunk_index(io.BytesIO(canonical_bytes(altered)), expected_digest=index.digest)
    with pytest.raises(WeightShardStoreError, match="pinned chunk index"):
        read_chunk_index(io.BytesIO(json.dumps(index.record(), indent=2).encode()),
                         expected_digest=index.digest)
    with pytest.raises(WeightShardStoreError, match="incomplete chunk index"):
        WeightChunkIndex(index.object_digest, index.object_bytes, CHUNK, ("a" * 64,))
    with pytest.raises(WeightShardStoreError, match="power of two"):
        WeightChunkIndex(index.object_digest, index.object_bytes, CHUNK + 1, index.chunk_sha256)


def test_completed_cursor_requires_explicit_prior_pin_for_restart(tmp_path):
    owner, _, _, index = setup(tmp_path)
    state = start_weight_range(owner, index, expected_index_digest=index.digest)
    result = step(owner, index, state, maximum_bytes=index.object_bytes, maximum_chunks=3)
    assert result["status"] == "completed"
    with pytest.raises(WeightShardStoreError, match="prior range campaign"):
        start_weight_range(owner, index, expected_index_digest=index.digest)
    new = start_weight_range(owner, index, expected_index_digest=index.digest,
                             prior_campaign_digest=result["campaign"]["digest"])
    assert new["verified_bytes"] == 0 and new["campaign_id"] != state["campaign_id"]
    with pytest.raises(WeightShardStoreError, match="exact completed"):
        check_completed_weight_range(owner, index, expected_index_digest=index.digest,
                                     campaign_digest=result["campaign"]["digest"])


def test_whole_object_indexing_refuses_read_ceiling_before_hashing(tmp_path, monkeypatch):
    owner, _, _, index = setup(tmp_path)
    from skeleton.ai.model_runtime import weight_store_range as module
    monkeypatch.setattr(module, "_read_range", lambda *a, **k: pytest.fail("read before index admission"))
    with pytest.raises(WeightShardStoreError, match="read ceiling"):
        build_weight_chunk_index(owner, object_digest=index.object_digest,
                                 object_bytes=index.object_bytes,
                                 maximum_bytes=index.object_bytes - 1, chunk_bytes=CHUNK)
