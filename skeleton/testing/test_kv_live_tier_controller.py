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

    def controller(self, samples, ticks=(1000, 1001, 1002, 1003)):
        observed = iter(samples)
        clock = iter(ticks)
        return KVLiveTierController(
            self.manager, storage_path=".", policy=self.policy,
            probe=lambda _: next(observed), clock=lambda: next(clock),
            simulated=True,
        )

    def test_cpu_pressure_demotes_with_two_fresh_samples(self):
        ctl = self.controller([host(), host(), host(), host()])
        plan, observation = ctl.plan_live()
        self.assertEqual(observation.sample.gpu_pressure_pct, None)
        self.assertFalse(observation.gpu_device_qualified)
        self.assertEqual({move.target for move in plan.moves}, {CacheTier.NVME})
        receipt = ctl.apply_live(plan)
        self.assertEqual(receipt.moved, self.keys)
        self.assertEqual(len(self.storage.moves), 1)


    def test_final_adapter_pressure_regression_quarantines_completion(self):
        # Planning, preflight and before_move are safe; the physical adapter
        # then succeeds, but a final OS probe reveals a concurrent disk loss.
        # The caller must keep durable RUNNING intent for reconciliation.
        ctl = self.controller([
            host(disk_free=900), host(disk_free=900),
            host(disk_free=900), host(disk_free=700),
        ])
        plan, _ = ctl.plan_live()
        self.assertEqual(len(plan.moves), 1)
        with self.assertRaisesRegex(KVPressureDeferred, "worsening"):
            ctl.apply_live(plan)
        self.assertEqual(len(self.storage.moves), 1)

    def test_final_probe_failure_never_claims_successful_receipt(self):
        ctl = self.controller([
            host(disk_free=900), host(disk_free=900),
            host(disk_free=900),
        ])
        plan, _ = ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "unavailable"):
            ctl.apply_live(plan)
        self.assertEqual(len(self.storage.moves), 1)

    def test_final_probe_accepts_only_accounted_disk_consumption(self):
        ctl = self.controller([
            host(disk_free=900), host(disk_free=900),
            host(disk_free=900), host(disk_free=772),
        ])
        plan, _ = ctl.plan_live()
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
            host(ram_free=50, swap_free=1000),
            host(ram_free=50, swap_free=1000),
        ])
        plan, _ = ctl.plan_live()
        receipt = ctl.apply_live(plan)
        self.assertEqual(receipt.moved, self.keys)

    def test_clock_regression_between_plan_and_apply_blocks_migration(self):
        ctl = self.controller(
            [host(), host()], ticks=(1000, 999),
        )
        plan, _ = ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "regressed"):
            ctl.apply_live(plan)
        self.assertEqual(self.storage.moves, [])

    def test_clock_regression_between_planning_rounds_is_not_fresh(self):
        ctl = self.controller(
            [host(), host()], ticks=(1000, 999),
        )
        ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "regressed"):
            ctl.plan_live()
        self.assertEqual(self.storage.moves, [])

    def test_stale_probe_prevents_any_movement(self):
        ctl = self.controller([host(), host()], ticks=(1000, 2000))
        plan, _ = ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "stale"):
            ctl.apply_live(plan)
        self.assertEqual(self.storage.moves, [])

    def test_second_page_pressure_deterioration_fences_remaining_moves(self):
        # Two independent resident pages. The first physical migration
        # succeeds; a worsening OS sample MUST prevent the second move.
        second = self.manager.commit_prefix(
            (3, 4), (KVPageInput("cpu-page-2", 128, tier=CacheTier.CPU),),
            self.namespace,
        )
        ctl = self.controller([
            host(), host(), host(), host(disk_free=700),
        ])
        plan, _ = ctl.plan_live()
        self.assertEqual(len(plan.moves), 2)
        with self.assertRaisesRegex(KVPressureDeferred, "worsening"):
            ctl.apply_live(plan)
        self.assertEqual(len(self.storage.moves), 1)
        self.assertIn(self.storage.moves[0][0], {"cpu-page", "cpu-page-2"})
        self.assertTrue(second)

    def test_exhausted_telemetry_fails_closed_before_move(self):
        ctl = self.controller([host(), host()])
        plan, _ = ctl.plan_live()
        with self.assertRaisesRegex(KVPressureDeferred, "unavailable"):
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
