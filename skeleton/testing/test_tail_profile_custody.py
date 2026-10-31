"""Durable tail profile tests with simulated independent CAS and CPU receipts."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.ai.model_runtime.tail_profile_custody import (
    DurableTailProfileStore, TailCustodyQuarantined,
)
from skeleton.ai.model_runtime.tail_latency_profile import (
    LocalTailProfiler, ProfileIdentity, ResourceObservation,
)
from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming

KEY = b"k" * 32


class Anchor:
    """In-memory test double, NOT production rollback protection."""

    def __init__(self):
        self.value = None
        self.fail_advance = False

    def initialize(self, *, generation, digest):
        if self.value is not None:
            raise ValueError("already initialized")
        self.value = generation, digest

    def read(self):
        if self.value is None:
            raise ValueError("missing anchor")
        return self.value

    def advance(self, *, expected_generation, expected_digest, generation, digest):
        if self.value != (expected_generation, expected_digest):
            raise ValueError("stale external CAS")
        if self.fail_advance:
            raise OSError("external anchor unavailable")
        self.value = generation, digest


def identity():
    return ProfileIdentity(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 40,
        "cpu", "simulated-cpu", "simulated",
    )


def record(profile, index):
    profile.record(
        ExecutionTiming(
            request_id=f"r-{index}", started_ns=0,
            first_token_ns=index * 1_000_000,
            completed_ns=(index + 10) * 1_000_000,
            output_tokens=10, prompt_tokens=20, prefix_reused_tokens=5,
        ),
        ResourceObservation(
            ram_available_bytes=1000, ram_total_bytes=2000,
            swap_free_bytes=100, swap_total_bytes=200,
            cpu_load_ppm=100000, thermal="unavailable",
        ),
    )


def make(connection, anchor=None):
    return DurableTailProfileStore(
        connection, anchor or Anchor(), key=KEY, identity=identity(),
    )


def test_bootstrap_append_restart_and_no_implicit_reset(tmp_path):
    path = tmp_path / "tail.db"
    anchor = Anchor()
    connection = sqlite3.connect(path)
    store = make(connection, anchor)
    profile = store.bootstrap()
    record(profile, 1)
    generation, digest = store.persist(profile)
    assert generation == 1 and len(digest) == 64
    connection.close()
    reopened = make(sqlite3.connect(path), anchor)
    loaded = reopened.load()
    assert loaded.checkpoint() == profile.checkpoint()
    record(loaded, 2)
    assert reopened.persist(loaded)[0] == 2
    assert len(reopened.load().checkpoint()["records"]) == 2
    with pytest.raises(TailCustodyQuarantined):
        reopened.bootstrap()


def test_replay_and_history_rewrite_denied():
    store = make(sqlite3.connect(":memory:"))
    profile = store.bootstrap()
    record(profile, 1)
    store.persist(profile)
    with pytest.raises(ValueError, match="no new"):
        store.persist(profile)
    modified = LocalTailProfiler(identity())
    record(modified, 2)
    with pytest.raises(ValueError, match="history"):
        store.persist(modified)
    assert len(store.load().checkpoint()["records"]) == 1


def test_anchor_failure_quarantines_without_retry(tmp_path):
    anchor = Anchor()
    store = make(sqlite3.connect(tmp_path / "tail.db"), anchor)
    profile = store.bootstrap()
    record(profile, 1)
    anchor.fail_advance = True
    with pytest.raises(TailCustodyQuarantined, match="publication"):
        store.persist(profile)
    assert store.quarantined
    with pytest.raises(TailCustodyQuarantined):
        store.load()
    # New process also refuses mismatched external CAS.
    reopened = make(sqlite3.connect(tmp_path / "tail.db"), anchor)
    with pytest.raises(TailCustodyQuarantined, match="unverifiable"):
        reopened.load()


def test_stored_payload_tampering_quarantines():
    connection = sqlite3.connect(":memory:")
    store = make(connection)
    store.bootstrap()
    connection.execute(
        "UPDATE local_tail_profile_custody SET payload = ?",
        (b'{"forged":true}',),
    )
    connection.commit()
    with pytest.raises(TailCustodyQuarantined):
        store.load()
    assert store.quarantined


def test_stored_mac_tampering_quarantines():
    connection = sqlite3.connect(":memory:")
    store = make(connection)
    store.bootstrap()
    connection.execute(
        "UPDATE local_tail_profile_custody SET mac = ?", ("0" * 64,),
    )
    connection.commit()
    with pytest.raises(TailCustodyQuarantined):
        store.load()


def test_wrong_key_or_identity_denied(tmp_path):
    path = tmp_path / "tail.db"
    anchor = Anchor()
    original = make(sqlite3.connect(path), anchor)
    original.bootstrap()
    wrong = DurableTailProfileStore(
        sqlite3.connect(path), anchor, key=b"x" * 32,
        identity=identity(),
    )
    with pytest.raises(TailCustodyQuarantined):
        wrong.load()


def test_bootstrap_failure_does_not_silently_recreate(tmp_path):
    path = tmp_path / "tail.db"
    anchor = Anchor()
    first = make(sqlite3.connect(path), anchor)
    first.bootstrap()
    second = make(sqlite3.connect(path), anchor)
    with pytest.raises(TailCustodyQuarantined):
        second.bootstrap()
    assert second.quarantined


def test_missing_external_anchor_denies_restart(tmp_path):
    path = tmp_path / "tail.db"
    original = make(sqlite3.connect(path))
    original.bootstrap()
    restarted = make(sqlite3.connect(path), Anchor())
    with pytest.raises(TailCustodyQuarantined):
        restarted.load()


def test_payload_byte_budget_fails_before_mutation(monkeypatch):
    from skeleton.ai.model_runtime import tail_profile_custody as module
    store = make(sqlite3.connect(":memory:"))
    profile = store.bootstrap()
    record(profile, 1)
    monkeypatch.setattr(module, "MAX_PAYLOAD_BYTES", 100)
    with pytest.raises(ValueError, match="byte budget"):
        store.persist(profile)
    assert not store.quarantined


def test_incorrect_schema_is_rejected():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE local_tail_profile_custody (singleton INTEGER)"
    )
    with pytest.raises(ValueError, match="schema"):
        make(connection)


def test_bool_generation_in_anchor_is_not_trusted():
    anchor = Anchor()
    store = make(sqlite3.connect(":memory:"), anchor)
    store.bootstrap()
    anchor.value = (True, anchor.value[1])
    with pytest.raises(TailCustodyQuarantined):
        store.load()
