"""Simulated app KV migration integration; no hardware qualification."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.app.offline_kv_migration import OfflineKVPageTierService
from skeleton.ai.runtime.inference.kv import (
    CacheTier, KVCacheConfig, KVCacheManager, KVNamespace,
    KVPageInput, TierPressurePolicy,
)
from skeleton.ai.runtime.inference.kv.live_tier_controller import KVLiveTierController
from skeleton.ai.runtime.inference.kv.migration_journal import (
    KVMigrationJournal, KVMigrationOutcomeUnknown,
)


class Storage:
    def __init__(self):
        self.calls = 0

    def move(self, handle, source, target):
        self.calls += 1
        return ("moved", handle, target)

    def release(self, handle, tier):
        pass


def host():
    return LocalResourceSnapshot(
        total_ram_bytes=1000, available_ram_bytes=50,
        total_disk_bytes=2000, free_disk_bytes=900,
        cpu_count=2, cpu_load_ratio=0.2,
        total_swap_bytes=1000, free_swap_bytes=1000,
    )


def simulated_service():
    storage = Storage()
    manager = KVCacheManager(
        KVCacheConfig(block_size_tokens=2, max_bytes=4096),
        storage=storage, clock=lambda: 1.0,
    )
    manager.commit_prefix(
        (1, 2), (KVPageInput("opaque", 128, tier=CacheTier.CPU),),
        KVNamespace("model", tokenizer_id="tokenizer"),
    )
    ticks = iter((1000, 1001))
    controller = KVLiveTierController(
        manager, storage_path=".",
        policy=TierPressurePolicy(
            min_disk_reserve_bytes=256, min_cpu_headroom_bytes=64,
            max_sample_age_ns=100, cooldown_ns=1,
        ),
        probe=lambda _: host(), clock=lambda: next(ticks),
        simulated=True,
    )
    journal = KVMigrationJournal(
        sqlite3.connect(":memory:"), session_id="a" * 64,
        journal_key=b"k" * 32,
    )
    return controller, journal, storage


def test_app_plans_and_commits_without_device_claims():
    controller, journal, storage = simulated_service()
    app = OfflineKVPageTierService(controller, journal, simulated=True)
    plan, status = app.plan_live()
    assert status.simulated
    assert status.planned_moves == 1
    assert not status.gpu_device_qualified
    completed = app.apply_once(plan)
    assert completed.moved == 1
    assert completed.rejected == 0
    assert storage.calls == 1
    with pytest.raises(KVMigrationOutcomeUnknown):
        app.apply_once(plan)
    assert storage.calls == 1


def test_app_rejects_unlabelled_simulated_probe():
    controller, journal, storage = simulated_service()
    with pytest.raises(ValueError, match="simulation"):
        OfflineKVPageTierService(controller, journal)


def test_app_requires_canonical_journal():
    controller, journal, storage = simulated_service()
    with pytest.raises(ValueError, match="journal"):
        OfflineKVPageTierService(controller, object(), simulated=True)


def test_app_rejects_invalid_simulation_flag():
    controller, journal, storage = simulated_service()
    with pytest.raises(ValueError, match="simulation"):
        OfflineKVPageTierService(controller, journal, simulated=1)


def test_app_exposes_authenticated_migration_inventory_without_device_claim():
    controller, journal, storage = simulated_service()
    service = OfflineKVPageTierService(controller, journal, simulated=True)
    inventory = service.verified_journal_status()
    assert inventory["rows"] == 0
    assert inventory["gpu_device_qualified"] is False
    plan, _ = service.plan_live()
    service.apply_once(plan)
    inventory = service.verified_journal_status()
    assert inventory["committed"] == 1
    assert inventory["running"] == 0
    assert inventory["gpu_device_qualified"] is False
