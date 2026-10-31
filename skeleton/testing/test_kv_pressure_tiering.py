"""Source-backed KV tier planning and fail-closed migration regressions.

The adapter here is explicitly simulated: no GPU/Metal/ROCm qualification.
"""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.inference.kv import (
    CacheTier, KVCacheConfig, KVCacheManager, KVNamespace, KVPageInput,
    KVPressureTierPlanner, TierPressurePolicy, TierPressureSample,
)


class SimulatedStorage:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.moves: list[tuple[object, CacheTier, CacheTier]] = []

    def move(self, handle: object, source: CacheTier, target: CacheTier) -> object:
        if self.fail:
            raise OSError("simulated adapter failure")
        self.moves.append((handle, source, target))
        return ("moved", handle, target)

    def release(self, handle: object, tier: CacheTier) -> None:
        pass


class KVPressureTieringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = SimulatedStorage()
        self.manager = KVCacheManager(
            KVCacheConfig(block_size_tokens=2, max_bytes=4096),
            storage=self.adapter, clock=lambda: 1.0,
        )
        self.namespace = KVNamespace("test-model", tokenizer_id="test-tokenizer")
        self.planner = KVPressureTierPlanner(
            TierPressurePolicy(min_disk_reserve_bytes=256, min_cpu_headroom_bytes=64,
                               max_sample_age_ns=1000, cooldown_ns=100)
        )

    def pages(self, *, pin: bool = False) -> tuple[str, ...]:
        return self.manager.commit_prefix(
            (1, 2, 3, 4),
            (KVPageInput("gpu-a", 128), KVPageInput("gpu-b", 128)),
            self.namespace, pin=pin,
        )

    def sample(self, *, gpu: int | None = 95, cpu: int | None = 20,
               cpu_free: int | None = 1000, disk_free: int | None = 1000) -> TierPressureSample:
        return TierPressureSample(1000, "simulated-test",
                                  gpu, cpu, cpu_free, disk_free)

    def test_gpu_to_cpu_measured_plan_and_receipt(self) -> None:
        keys = self.pages()
        plan = self.planner.plan(self.manager, self.sample(), now_ns=1001)
        self.assertEqual({move.page_key for move in plan.moves}, set(keys))
        self.assertEqual({move.target for move in plan.moves}, {CacheTier.CPU})
        receipt = self.planner.apply(self.manager, plan, now_ns=1001)
        self.assertEqual(set(receipt.moved), set(keys))
        self.assertEqual(receipt.rejected, ())
        self.assertEqual({p.tier for p in self.manager.tier_inventory()}, {CacheTier.CPU})
        self.assertEqual(self.manager.stats().migrations, 2)

    def test_unknown_measurements_never_demote(self) -> None:
        self.pages()
        plan = self.planner.plan(self.manager, self.sample(gpu=None, cpu=None,
                                cpu_free=None, disk_free=None), now_ns=1001)
        self.assertEqual(plan.moves, ())

    def test_disk_reserve_prevents_demote(self) -> None:
        self.pages()
        plan = self.planner.plan(self.manager, self.sample(cpu=98, cpu_free=None,
                                 disk_free=260), now_ns=1001)
        self.assertEqual(plan.moves, ())

    def test_pinned_pages_never_migrate(self) -> None:
        self.pages(pin=True)
        plan = self.planner.plan(self.manager, self.sample(), now_ns=1001)
        self.assertEqual(plan.moves, ())

    def test_stale_sample_and_forged_plan_rejected(self) -> None:
        self.pages()
        with self.assertRaisesRegex(ValueError, "stale"):
            self.planner.plan(self.manager, self.sample(), now_ns=3000)
        plan = self.planner.plan(self.manager, self.sample(), now_ns=1001)
        self.manager.pin((plan.moves[0].page_key,))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.planner.apply(self.manager, plan, now_ns=1001)

    def test_adapter_failure_returns_explicit_partial_receipt(self) -> None:
        self.pages()
        self.adapter.fail = True
        plan = self.planner.plan(self.manager, self.sample(), now_ns=1001)
        receipt = self.planner.apply(self.manager, plan, now_ns=1001)
        self.assertEqual(receipt.moved, ())
        self.assertEqual(len(receipt.rejected), 2)
        self.assertEqual(self.manager.stats().storage_errors, 2)
        self.assertEqual({p.tier for p in self.manager.tier_inventory()}, {CacheTier.GPU})

    def test_cooldown_prevents_immediate_repeated_migration(self) -> None:
        self.pages()
        plan = self.planner.plan(self.manager, self.sample(), now_ns=1001)
        self.planner.apply(self.manager, plan, now_ns=1001)
        later = TierPressureSample(1002, "simulated-test", 99, 99, 0, 1000)
        self.assertEqual(self.planner.plan(self.manager, later, now_ns=1003).moves, ())

    def test_invalid_telemetry_is_rejected(self) -> None:
        for bad in (True, -1, 101, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    TierPressureSample(1, "probe", gpu_pressure_pct=bad)


if __name__ == "__main__":
    unittest.main()
