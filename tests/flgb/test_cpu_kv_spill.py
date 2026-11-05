"""CPU reference-KV spill/restore against the real transformer."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.cortex.transformer import KVCache, TinyTransformer
from skeleton.ai.model_runtime.cpu_kv_spill import CpuKVSpillError, CpuKVSpillStore
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError


class TestCpuKVSpill(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "kv"
        self.store = CpuKVSpillStore(self.root, disk_reserve_bytes=0)
        self.model = TinyTransformer(
            vocab=("hello", "world", "again"), dim=8, ctx=8, seed=7,
            n_heads=2, n_layers=2, d_ff=16,
        )
        self.runtime = NativeLLMRuntime(self.model)
        self.cache = KVCache(self.model.n_layers, self.model.ctx)
        self.logits = self.model._logits_window([1, 2, 3], self.cache)

    def test_round_trip_preserves_actual_reference_logits(self):
        digest = self.runtime.spill_cpu_kv(self.cache, self.store)
        restored = self.runtime.restore_cpu_kv(digest, self.store)
        self.assertEqual(restored.K, self.cache.K)
        self.assertEqual(restored.V, self.cache.V)
        self.assertEqual(restored.tokens, [1, 2, 3])
        self.assertEqual(self.model._logits_window([1, 2, 3], restored), self.logits)
        self.assertEqual(self.model._logits_window([1, 2, 3, 2], restored),
                         self.model._logits_window([1, 2, 3, 2], self.cache))

    def test_restored_cache_is_reachable_through_public_inference(self):
        digest = self.runtime.spill_cpu_kv(self.cache, self.store)
        restored = self.runtime.restore_cpu_kv(digest, self.store)
        sequence = TokenSequence(
            self.runtime.tokenizer.digest, (1, 2, 3), sha256(b"exact-source").hexdigest(),
        )
        result = self.runtime.infer_sequence(sequence, cache=restored)
        self.assertEqual(result.logits, tuple(self.logits))
        self.assertEqual(result.cache_tokens, 3)
        with self.assertRaises(RuntimeContractError):
            self.runtime.infer_sequence(sequence, use_cache=False, cache=restored)

    def test_explicit_cache_cannot_cross_model_ownership(self):
        sequence = TokenSequence(
            self.runtime.tokenizer.digest, (1, 2, 3), sha256(b"exact-source").hexdigest(),
        )
        other = KVCache(self.model.n_layers, self.model.ctx)
        other.owner = object()
        with self.assertRaises(RuntimeContractError):
            self.runtime.infer_sequence(sequence, cache=other)

    def test_restart_store_and_idempotence(self):
        digest = self.store.stage(self.runtime, self.cache)
        restarted = CpuKVSpillStore(self.root, disk_reserve_bytes=0)
        self.assertEqual(restarted.stage(self.runtime, self.cache), digest)
        self.assertEqual(restarted.restore(self.runtime, digest).tokens, [1, 2, 3])

    def test_concurrent_immutable_publication(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            digests = list(pool.map(lambda _: self.store.stage(self.runtime, self.cache), range(8)))
        self.assertEqual(len(set(digests)), 1)

    def test_corrupt_bytes_fail_closed(self):
        digest = self.store.stage(self.runtime, self.cache)
        self.store._path(digest).write_bytes(b"corrupt")
        with self.assertRaises(CpuKVSpillError):
            self.store.restore(self.runtime, digest)

    def test_wrong_model_identity_rejected(self):
        digest = self.store.stage(self.runtime, self.cache)
        other = NativeLLMRuntime(TinyTransformer(
            vocab=("hello", "world", "again"), dim=8, ctx=8, seed=11,
            n_heads=2, n_layers=2, d_ff=16,
        ))
        with self.assertRaises(CpuKVSpillError):
            self.store.restore(other, digest)

    def test_mutated_model_is_not_accepted(self):
        digest = self.store.stage(self.runtime, self.cache)
        self.model.E[0][0] += 0.01
        with self.assertRaises(RuntimeContractError):
            self.store.restore(self.runtime, digest)

    def test_reject_stale_cache_revision(self):
        self.cache.revision = ("wrong",)
        with self.assertRaises(CpuKVSpillError):
            self.store.stage(self.runtime, self.cache)

    def test_reject_accelerator_occupancy_mirror(self):
        self.cache.reserved_bytes = 100
        with self.assertRaises(CpuKVSpillError):
            self.store.stage(self.runtime, self.cache)

    def test_reject_invalid_shapes_before_publication(self):
        self.cache.K[0][0] = [float("nan")] * self.model.dim
        with self.assertRaises(CpuKVSpillError):
            self.store.stage(self.runtime, self.cache)

    def test_reject_token_axis_mismatch(self):
        self.cache.V[0].pop()
        with self.assertRaises(CpuKVSpillError):
            self.store.stage(self.runtime, self.cache)

    def test_reject_nonresident_cpu_policy_violation(self):
        self.model.resident = True
        with self.assertRaises(CpuKVSpillError):
            self.store.stage(self.runtime, self.cache)

    def test_reject_disk_reserve_exhaustion(self):
        reserved = CpuKVSpillStore(
            self.root / "reserved", disk_reserve_bytes=2**60,
        )
        with self.assertRaises(CpuKVSpillError):
            reserved.stage(self.runtime, self.cache)

    def test_reject_overbudget(self):
        tiny = CpuKVSpillStore(self.root / "tiny", max_snapshot_bytes=1,
                               disk_reserve_bytes=0)
        with self.assertRaises(CpuKVSpillError):
            tiny.stage(self.runtime, self.cache)

    def test_reject_symlinked_spill(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unavailable")
        digest = self.store.stage(self.runtime, self.cache)
        path = self.store._path(digest)
        saved = path.with_name("original")
        path.rename(saved)
        try:
            path.symlink_to(saved)
        except (OSError, NotImplementedError):
            self.skipTest("symlink permission unavailable")
        with self.assertRaises(CpuKVSpillError):
            self.store.restore(self.runtime, digest)

    def test_reject_missing_object(self):
        with self.assertRaises(CpuKVSpillError):
            self.store.restore(self.runtime, "0" * 64)


if __name__ == "__main__":
    unittest.main()
