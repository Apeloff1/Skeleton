"""Simulated OS resource and KV adapter tests; no device qualification."""
from __future__ import annotations

import unittest

from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.ai.runtime.inference.kv import (
    CacheTier, KVCacheConfig, KVCacheManager, KVNamespace, KVPageInput,
    TierPressurePolicy,
)
from skeleton.ai.runtime.inference.kv.live_tier_controller import (
    KVLiveTierController, KVPressureDeferred,
)


class Storage:
    def __init__(self):
        self.moves = []

    def move(self, handle, source, target):
        self.moves.append((handle, source, target))
        return ("moved", handle, target)

    def release(self, handle, tier):
        pass


def host(*, ram_free=50, disk_free=900, swap_free=1000):
    return LocalResourceSnapshot(
        total_ram_bytes=1000, available_ram_bytes=ram_free,
        total_disk_bytes=2000, free_disk_bytes=disk_free,
        cpu_count=2, cpu_load_ratio=0.2,
        total_swap_bytes=1000, free_swap_bytes=swap_free,
    )


class KVLiveTierTests(unittest.TestCase):
    def setUp(self):
        self.storage = Storage()
        self.manager = KVCacheManager(
            KVCacheConfig(block_size_tokens=2, max_bytes=4096),
            storage=self.storage, clock=lambda: 1.0,
        )
        self.namespace = KVNamespace("local-model", tokenizer_id="local-tokenizer")
        self.keys = self.manager.commit_prefix(
            (1, 2), (KVPageInput("cpu-page", 128, tier=CacheTier.CPU),),
            self.namespace,
        )
        self.policy = TierPressurePolicy(
            min_disk_reserve_bytes=256, min_cpu_headroom_bytes=64,
            max_sample_age_ns=100, cooldown_ns=1,
        )

    def controller(self, samples, ticks=(1000, 1001)):
        observed = iter(samples)
        clock = iter(ticks)
        return KVLiveTierController(
            self.manager, storage_path=".", policy=self.policy,
            probe=lambda _: next(observed), clock=lambda: next(clock),
            simulated=True,
        )

    def test_cpu_pressure_demotes_with_two_fresh_samples(self):
        ctl = self.controller([host(), host()])
        plan, observation = ctl.plan_live()
        self.assertEqual(observation.sample.gpu_pressure_pct, None)
        self.assertFalse(observation.gpu_device_qualified)
        self.assertEqual({move.target for move in plan.moves}, {CacheTier.NVME})
        receipt = ctl.apply_live(plan)
        self.assertEqual(receipt.moved, self.keys)
        self.assertEqual(len(self.storage.moves), 1)

    def test_falling_disk_headroom_prevents_any_movement(self):
        ctl = self.controller([host(), host(disk_free=700)])
        plan, _ = ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "worsening"):
            ctl.apply_live(plan)
        self.assertEqual(self.storage.moves, [])

    def test_swap_pressure_increase_blocks_even_when_ram_headroom_is_unchanged(self):
        # RAM and disk capacity stay unchanged; worsening swap pressure
        # must not be hidden by a superficially stable byte headroom check.
        ctl = self.controller([
            host(ram_free=50, disk_free=900, swap_free=1000),
            host(ram_free=50, disk_free=900, swap_free=0),
        ])
        plan, _ = ctl.plan_live()
        self.assertTrue(plan.moves)
        with self.assertRaisesRegex(KVPressureDeferred, "worsening"):
            ctl.apply_live(plan)
        self.assertEqual(self.storage.moves, [])

    def test_stable_swap_pressure_remains_eligible(self):
        ctl = self.controller([
            host(ram_free=50, swap_free=1000),
            host(ram_free=50, swap_free=1000),
        ])
        plan, _ = ctl.plan_live()
        receipt = ctl.apply_live(plan)
        self.assertEqual(receipt.moved, self.keys)

    def test_stale_probe_prevents_any_movement(self):
        ctl = self.controller([host(), host()], ticks=(1000, 2000))
        plan, _ = ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "stale"):
            ctl.apply_live(plan)
        self.assertEqual(self.storage.moves, [])

    def test_unknown_gpu_never_causes_gpu_demote(self):
        self.manager.commit_prefix(
            (3, 4), (KVPageInput("gpu-page", 128),), self.namespace,
        )
        ctl = self.controller([host()])
        plan, _ = ctl.plan_live()
        self.assertNotIn(CacheTier.GPU, {move.source for move in plan.moves})

    def test_untrusted_injected_probe_must_be_simulated(self):
        with self.assertRaisesRegex(ValueError, "simulated"):
            KVLiveTierController(
                self.manager, storage_path=".", probe=lambda _: host(),
                simulated=False,
            )

    def test_pinned_pages_remain_resident(self):
        self.manager.pin(self.keys)
        ctl = self.controller([host()])
        plan, _ = ctl.plan_live()
        self.assertEqual(plan.moves, ())

    def test_no_disk_reserve_no_migration(self):
        ctl = self.controller([host(disk_free=260)])
        plan, _ = ctl.plan_live()
        self.assertEqual(plan.moves, ())


if __name__ == "__main__":
    unittest.main()
