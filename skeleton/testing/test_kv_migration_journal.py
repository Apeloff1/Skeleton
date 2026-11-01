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
    # An adapter exception may occur AFTER a physical side effect. The
    # journal must stay RUNNING; a rejected receipt cannot certify no move.
    with pytest.raises(KVMigrationOutcomeUnknown, match="uncertain"):
        service.apply_once(plan)
    assert storage.calls == 1
    with pytest.raises(KVMigrationOutcomeUnknown, match="unresolved"):
        journal.begin(plan)
    with pytest.raises(KVMigrationOutcomeUnknown, match="committed"):
        journal.recover_committed(plan)
    assert storage.calls == 1


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


def test_verified_history_rejects_tampered_committed_plan_before_new_move():
    connection = sqlite3.connect(":memory:")
    service, journal, storage = setup(connection=connection)
    plan, _ = service.plan_live()
    service.apply_once(plan)
    assert journal.verified_inventory()["committed"] == 1
    connection.execute(
        "UPDATE local_kv_migration_journal SET plan_mac = ?",
        ("0" * 64,),
    )
    connection.commit()
    with pytest.raises(KVMigrationOutcomeUnknown, match="unverifiable"):
        journal.verified_inventory()
    with pytest.raises(KVMigrationOutcomeUnknown, match="unverifiable"):
        journal.begin(plan)
    assert storage.calls == 1


def test_verified_history_distinguishes_running_without_replaying():
    service, journal, storage = setup()
    plan, _ = service.plan_live()
    journal.begin(plan)
    inventory = journal.verified_inventory()
    assert inventory["rows"] == 1
    assert inventory["running"] == 1
    assert inventory["committed"] == 0
    with pytest.raises(KVMigrationOutcomeUnknown, match="unresolved"):
        journal.begin(plan)
    assert storage.calls == 0


def test_verified_history_rejects_forged_receipt_accounting():
    connection = sqlite3.connect(":memory:")
    service, journal, storage = setup(connection=connection)
    plan, _ = service.plan_live()
    service.apply_once(plan)
    from skeleton.ai.runtime.inference.kv import migration_journal as module
    fake = {
        "schema": "skeleton.ai.kv-pressure-apply.v1",
        "plan_digest": plan.digest,
        "moved": [],
        "rejected": [],
    }
    connection.execute(
        "UPDATE local_kv_migration_journal SET receipt_payload=?, receipt_mac=?",
        (module._encode(fake), module._sign(KEY, fake)),
    )
    connection.commit()
    with pytest.raises(KVMigrationOutcomeUnknown, match="unverifiable"):
        journal.verified_inventory()
    assert storage.calls == 1


class SimulatedMigrationCAS:
    """Independent simulated anchor, NOT a production durable implementation."""

    def __init__(self):
        self.value = None
        self.fail_advance = False

    def initialize(self, *, generation, digest):
        if self.value is not None:
            raise ValueError("anchor already initialized")
        self.value = (generation, digest)

    def read(self):
        if self.value is None:
            raise ValueError("anchor missing")
        return self.value

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.fail_advance or self.value != (expected_generation, expected_digest):
            raise ValueError("external CAS refused")
        self.value = (generation, digest)


def test_independent_anchor_detects_sqlite_history_rollback():
    connection = sqlite3.connect(":memory:")
    anchor = SimulatedMigrationCAS()
    service, journal, storage = setup(connection=connection)
    journal._anchor = anchor  # test-only binding before first installation
    journal.bootstrap_anchor()
    plan, _ = service.plan_live()
    service.apply_once(plan)
    assert anchor.value[0] == 2  # RUNNING intent, then committed receipt
    assert journal.verified_inventory()["committed"] == 1
    connection.execute("DELETE FROM local_kv_migration_journal")
    connection.commit()
    with pytest.raises(KVMigrationOutcomeUnknown, match="anchor unverifiable"):
        journal.verified_inventory()
    assert storage.calls == 1


def test_external_anchor_cas_failure_quarantines_after_sqlite_commit():
    connection = sqlite3.connect(":memory:")
    anchor = SimulatedMigrationCAS()
    service, journal, storage = setup(connection=connection)
    journal._anchor = anchor
    journal.bootstrap_anchor()
    plan, _ = service.plan_live()
    anchor.fail_advance = True
    with pytest.raises(KVMigrationOutcomeUnknown, match="anchor uncertain"):
        journal.begin(plan)
    assert journal._quarantined
    assert connection.execute(
        "SELECT state FROM local_kv_migration_journal"
    ).fetchone() == ("running",)
    assert storage.calls == 0
    with pytest.raises(KVMigrationOutcomeUnknown):
        journal.begin(plan)


def test_anchor_bootstrap_cannot_reset_existing_migration_history():
    connection = sqlite3.connect(":memory:")
    anchor = SimulatedMigrationCAS()
    service, journal, storage = setup(connection=connection)
    journal._anchor = anchor
    journal.bootstrap_anchor()
    with pytest.raises(KVMigrationOutcomeUnknown, match="bootstrap"):
        journal.bootstrap_anchor()
    assert journal._quarantined
    assert storage.calls == 0


def test_concurrent_anchor_advance_invalidates_read_only_inventory():
    connection = sqlite3.connect(":memory:")
    anchor = SimulatedMigrationCAS()
    service, journal, storage = setup(connection=connection)
    journal._anchor = anchor
    journal.bootstrap_anchor()
    reads = 0

    def racing_read():
        nonlocal reads
        reads += 1
        if reads == 2:
            anchor.value = (1, "f" * 64)
        return anchor.value

    anchor.read = racing_read
    with pytest.raises(KVMigrationOutcomeUnknown, match="anchor unverifiable"):
        journal.verified_inventory()
    assert reads == 2
    assert journal._quarantined
    assert storage.calls == 0


def test_concurrent_anchor_advance_invalidates_committed_receipt_read():
    connection = sqlite3.connect(":memory:")
    anchor = SimulatedMigrationCAS()
    service, journal, storage = setup(connection=connection)
    journal._anchor = anchor
    journal.bootstrap_anchor()
    plan, _ = service.plan_live()
    service.apply_once(plan)
    reads = 0

    def racing_read():
        nonlocal reads
        reads += 1
        if reads == 2:
            anchor.value = (anchor.value[0] + 1, "f" * 64)
        return anchor.value

    anchor.read = racing_read
    with pytest.raises(KVMigrationOutcomeUnknown, match="anchor unverifiable"):
        journal.recover_committed(plan)
    assert reads == 2
    assert journal._quarantined
    assert storage.calls == 1
