"""Simulated KV migration journal; no physical GPU or disk qualification."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.app.offline_resources import LocalResourceSnapshot
from skeleton.ai.runtime.inference.kv import (
    CacheTier, KVCacheConfig, KVCacheManager, KVNamespace,
    KVPageInput, TierPressurePolicy,
)
from skeleton.ai.runtime.inference.kv.live_tier_controller import KVLiveTierController
from skeleton.ai.runtime.inference.kv.migration_journal import (
    KVMigrationJournal, KVJournaledTierController,
    KVMigrationOutcomeUnknown,
)

SESSION = "a" * 64
KEY = b"k" * 32


class Storage:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def move(self, handle, source, target):
        self.calls += 1
        if self.fail:
            raise OSError("simulated partial physical migration")
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


def setup(*, fail=False, connection=None):
    storage = Storage(fail=fail)
    manager = KVCacheManager(
        KVCacheConfig(block_size_tokens=2, max_bytes=4096),
        storage=storage, clock=lambda: 1.0,
    )
    namespace = KVNamespace("model", tokenizer_id="tokenizer")
    manager.commit_prefix(
        (1, 2), (KVPageInput("opaque", 128, tier=CacheTier.CPU),),
        namespace,
    )
    clock = iter((1000, 1001))
    controller = KVLiveTierController(
        manager, storage_path=".",
        policy=TierPressurePolicy(
            min_disk_reserve_bytes=256, min_cpu_headroom_bytes=64,
            max_sample_age_ns=100, cooldown_ns=1,
        ),
        probe=lambda _: host(), clock=lambda: next(clock), simulated=True,
    )
    journal = KVMigrationJournal(
        connection or sqlite3.connect(":memory:"),
        session_id=SESSION, journal_key=KEY,
    )
    return KVJournaledTierController(controller, journal), journal, storage


def test_durable_intent_and_committed_receipt_restart(tmp_path):
    path = tmp_path / "migration.db"
    connection = sqlite3.connect(path)
    service, journal, storage = setup(connection=connection)
    plan, _ = service.plan_live()
    receipt = service.apply_once(plan)
    assert len(receipt.moved) == 1
    assert storage.calls == 1
    connection.close()
    restarted = KVMigrationJournal(
        sqlite3.connect(path), session_id=SESSION, journal_key=KEY,
    )
    assert restarted.recover_committed(plan)["moved"] == list(receipt.moved)
    with pytest.raises(KVMigrationOutcomeUnknown, match="consumed"):
        restarted.begin(plan)
    assert storage.calls == 1


def test_backend_failure_is_not_automatically_retried(tmp_path):
    path = tmp_path / "migration.db"
    connection = sqlite3.connect(path)
    service, journal, storage = setup(fail=True, connection=connection)
    plan, _ = service.plan_live()
    # The planner returns a partial failure receipt, not a fake success.
    receipt = service.apply_once(plan)
    assert receipt.moved == ()
    assert len(receipt.rejected) == 1
    assert storage.calls == 1
    with pytest.raises(KVMigrationOutcomeUnknown, match="consumed"):
        journal.begin(plan)


def test_crash_between_intent_and_backend_fences_restart(tmp_path):
    path = tmp_path / "migration.db"
    connection = sqlite3.connect(path)
    service, journal, storage = setup(connection=connection)
    plan, _ = service.plan_live()
    journal.begin(plan)
    connection.close()
    restarted = KVMigrationJournal(
        sqlite3.connect(path), session_id=SESSION, journal_key=KEY,
    )
    with pytest.raises(KVMigrationOutcomeUnknown, match="committed"):
        restarted.recover_committed(plan)
    with pytest.raises(KVMigrationOutcomeUnknown, match="unresolved"):
        restarted.begin(plan)
    assert storage.calls == 0


def test_receipt_tampering_is_rejected():
    connection = sqlite3.connect(":memory:")
    service, journal, storage = setup(connection=connection)
    plan, _ = service.plan_live()
    service.apply_once(plan)
    connection.execute(
        "UPDATE local_kv_migration_journal SET receipt_payload = ?",
        (b'{"forged":true}',),
    )
    connection.commit()
    with pytest.raises(KVMigrationOutcomeUnknown, match="corrupted"):
        journal.recover_committed(plan)


def test_wrong_session_and_key_cannot_recover():
    connection = sqlite3.connect(":memory:")
    service, journal, storage = setup(connection=connection)
    plan, _ = service.plan_live()
    service.apply_once(plan)
    wrong = KVMigrationJournal(
        connection, session_id="b" * 64, journal_key=b"x" * 32,
    )
    with pytest.raises(KVMigrationOutcomeUnknown):
        wrong.recover_committed(plan)


def test_invalid_journal_schema_fails_closed():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE local_kv_migration_journal (plan_digest TEXT)"
    )
    with pytest.raises(ValueError, match="schema"):
        KVMigrationJournal(
            connection, session_id=SESSION, journal_key=KEY,
        )


def test_replay_fenced_before_second_adapter_call():
    service, journal, storage = setup()
    plan, _ = service.plan_live()
    service.apply_once(plan)
    with pytest.raises(KVMigrationOutcomeUnknown, match="consumed"):
        service.apply_once(plan)
    assert storage.calls == 1


def test_journal_capacity_fail_closed(monkeypatch):
    from skeleton.ai.runtime.inference.kv import migration_journal as module
    service, journal, storage = setup()
    plan, _ = service.plan_live()
    monkeypatch.setattr(module, "MAX_ROWS", 0)
    with pytest.raises(KVMigrationOutcomeUnknown, match="capacity"):
        journal.begin(plan)
    assert storage.calls == 0
