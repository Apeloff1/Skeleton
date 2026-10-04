"""Restart, transaction, corruption and recovery gates for candidate lifecycle."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import replace
from threading import Barrier

import pytest

from skeleton.ai.runtime.learning_foundation.lifecycle import (
    ModelLifecycleError,
    ModelLifecycleRegistry,
    ModelLifecycleState,
)
from skeleton.ai.runtime.learning_foundation.lifecycle_repository import (
    MAX_SNAPSHOT_BYTES,
    LifecycleSnapshotTransaction,
    ModelLifecyclePersistenceError,
    SQLiteModelLifecycleRepository,
)
from skeleton.testing.test_p3_model_migration import (
    _decision,
    _mbom,
    _registry,
    _rollback,
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _stored(path):
    with closing(sqlite3.connect(path)) as connection:
        version, payload, digest = connection.execute(
            "SELECT version,payload,digest FROM lifecycle_state"
        ).fetchone()
    return version, json.loads(payload), digest


def _rewrite(path, edit):
    version, snapshot, _ = _stored(path)
    edit(snapshot)
    _replace_payload(path, _canonical(snapshot), version=version)


def _replace_payload(path, payload, *, version=None):
    with closing(sqlite3.connect(path)) as connection:
        digest = hashlib.sha256(payload.encode()).hexdigest()
        if version is None:
            connection.execute("UPDATE lifecycle_state SET payload=?,digest=?", (payload, digest))
        else:
            connection.execute(
                "UPDATE lifecycle_state SET version=?,payload=?,digest=?", (version, payload, digest)
            )
        connection.commit()


def _applied(path, **budgets):
    registry, source, target = _registry(path=path, **budgets)
    decision = _decision(registry, source, target)
    migration = registry.apply_migration(decision)
    return registry, source, target, decision, migration


def test_default_memory_api_and_injected_repository_remain_compatible(tmp_path):
    memory = ModelLifecycleRegistry()
    assert not memory.durable and memory.snapshot_version == 0
    with pytest.raises(ModelLifecycleError, match="cannot create a durable backup"):
        memory.backup(tmp_path / "memory.sqlite")
    repository = SQLiteModelLifecycleRepository(tmp_path / "injected.sqlite")
    registry = ModelLifecycleRegistry(repository=repository)
    assert registry.durable and registry.snapshot_version == 1
    registry.register_candidate(_mbom("candidate"))
    assert ModelLifecycleRegistry(path=repository.path).mbom(_mbom("candidate").model_digest) == _mbom(
        "candidate"
    )


def test_restart_reconstructs_exact_issued_evidence_and_preserves_baseline(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path, max_transitions=7)
    decision = _decision(registry, source, target)
    evidence = registry.migration_evaluation(decision)
    reopened = ModelLifecycleRegistry(path=path)
    issued = reopened.decision(decision.decision_digest)
    assert issued == decision and issued is not decision
    assert reopened.migration_evaluation(issued) == evidence
    assert reopened.mbom(source.model_digest) == source
    assert reopened.mbom(target.model_digest) == target
    assert reopened.history == registry.history
    for forged in (decision, replace(issued)):
        with pytest.raises(ModelLifecycleError, match="not issued by this registry"):
            reopened.apply_migration(forged)
    migration = reopened.apply_migration(issued)
    again = ModelLifecycleRegistry(path=path)
    version = again.snapshot_version
    assert again.apply_migration(again.decision(decision.decision_digest)) == migration
    assert again.snapshot_version == version
    assert registry.apply_migration(decision) == migration
    assert registry.state(source.model_digest) is ModelLifecycleState.DEPRECATED
    assert registry.state(target.model_digest) is ModelLifecycleState.ACTIVE


def test_apply_rollback_and_receipt_replay_survive_multiple_restarts(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target, decision, migration = _applied(path)
    reopened = ModelLifecycleRegistry(path=path)
    rollback = _rollback(reopened, reopened.migrations[0])
    restored = ModelLifecycleRegistry(path=path)
    version = restored.snapshot_version
    assert restored.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert restored.state(target.model_digest) is ModelLifecycleState.VALIDATED
    assert restored.history == registry.history
    assert restored.rollbacks == (rollback,)
    assert _rollback(restored, restored.migrations[0]) == rollback
    assert restored.apply_migration(restored.decision(decision.decision_digest)) == migration
    assert restored.snapshot_version == version
    with pytest.raises(ModelLifecycleError, match="replay changed"):
        _rollback(restored, restored.migrations[0], verifier_id="changed-verifier")


def test_restart_retains_rollback_reservations_and_budget_fences(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    _, source, _, _, _ = _applied(path, max_transitions=7)
    reopened = ModelLifecycleRegistry(path=path)
    with pytest.raises(ModelLifecycleError, match="history budget exhausted"):
        reopened.transition(
            source.model_digest,
            ModelLifecycleState.RETIRED,
            verifier_id="retirement-verifier",
            evidence_refs=("retire:source",),
        )
    _rollback(reopened, reopened.migrations[0])
    assert len(ModelLifecycleRegistry(path=path).history) == 7
    with pytest.raises(ModelLifecycleError, match="conflicts with persisted budget"):
        ModelLifecycleRegistry(path=path, max_transitions=8)


def test_stale_pre_rollback_decision_stays_stale_after_restart(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path)
    first = _decision(registry, source, target)
    pending = _decision(registry, source, target, evaluation_refs=("eval:second", "eval:third"))
    migration = registry.apply_migration(first)
    _rollback(registry, migration)
    reopened = ModelLifecycleRegistry(path=path)
    with pytest.raises(ModelLifecycleError, match="identity is stale"):
        reopened.apply_migration(reopened.decision(pending.decision_digest))
    assert _decision(reopened, source, target).decision_digest != first.decision_digest


def test_read_and_exact_replay_do_not_advance_snapshot_version(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path)
    decision = _decision(registry, source, target)
    version = registry.snapshot_version
    assert _decision(registry, source, target) is decision
    registry.register_candidate(source)
    registry.state(source.model_digest)
    assert len(registry.history) == 3
    registry.mbom(source.model_digest)
    registry.migration_evaluation(decision)
    assert registry.snapshot_version == version
    assert ModelLifecycleRegistry(path=path).snapshot_version == version


def test_live_registry_fences_regressed_versions_and_valid_history_replacement(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path)
    old_version, old_snapshot, _ = _stored(path)
    registry.apply_migration(_decision(registry, source, target))
    current_version = registry.snapshot_version
    _replace_payload(path, _canonical(old_snapshot), version=old_version)
    with pytest.raises(ModelLifecycleError, match="regressed"):
        _ = registry.history
    _replace_payload(path, _canonical(old_snapshot), version=current_version + 1)
    for _ in range(2):
        with pytest.raises(ModelLifecycleError, match="rewrote immutable history"):
            _ = registry.history


def test_same_version_recomputed_candidate_rebinding_is_detected_by_live_registry(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry = ModelLifecycleRegistry(path=path)
    registry.register_candidate(_mbom("candidate"))
    _rewrite(path, lambda snapshot: snapshot["mboms"][0].update(rights_refs=["rights:rebound"]))
    with pytest.raises(ModelLifecycleError, match="sequence or digest regressed"):
        registry.mbom(_mbom("candidate").model_digest)


def test_two_independent_connections_serialize_competing_model_migrations(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    first, source, target = _registry(path=path)
    challenger = first.register_candidate(_mbom("challenger"))
    first.transition(
        challenger.model_digest,
        ModelLifecycleState.VALIDATED,
        verifier_id="validation-verifier",
        evidence_refs=("eval:quality", "eval:safety"),
    )
    second = ModelLifecycleRegistry(path=path)
    decisions = (_decision(first, source, target), _decision(second, source, challenger))
    barrier = Barrier(2)

    def apply(pair):
        registry, decision = pair
        barrier.wait(timeout=5)
        try:
            return registry.apply_migration(decision)
        except ModelLifecycleError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(apply, zip((first, second), decisions)))
    assert sum(isinstance(result, ModelLifecycleError) for result in results) == 1
    reopened = ModelLifecycleRegistry(path=path)
    assert len(reopened.migrations) == 1
    assert (
        sum(
            reopened.state(model.model_digest) is ModelLifecycleState.ACTIVE for model in (target, challenger)
        )
        == 1
    )
    assert first.history == second.history == reopened.history


def test_two_connections_apply_same_decision_exactly_once(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    first, source, target = _registry(path=path)
    decision = _decision(first, source, target)
    second = ModelLifecycleRegistry(path=path)
    decisions = (decision, second.decision(decision.decision_digest))
    before_version = first.snapshot_version
    barrier = Barrier(2)

    def apply(pair):
        registry, issued = pair
        barrier.wait(timeout=5)
        return registry.apply_migration(issued)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(apply, zip((first, second), decisions)))
    assert results[0] == results[1]
    assert first.snapshot_version == second.snapshot_version == before_version + 1
    assert len(ModelLifecycleRegistry(path=path).history) == 5


def test_transaction_write_failure_rolls_back_both_models_and_cache(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path)
    decision = _decision(registry, source, target)
    before = _stored(path)
    save = LifecycleSnapshotTransaction.save

    def fail_after_write(transaction, snapshot):
        save(transaction, snapshot)
        raise ModelLifecyclePersistenceError("injected disk failure")

    with monkeypatch.context() as patch:
        patch.setattr(LifecycleSnapshotTransaction, "save", fail_after_write)
        with pytest.raises(ModelLifecyclePersistenceError, match="injected disk failure"):
            registry.apply_migration(decision)
    assert _stored(path) == before
    assert registry.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert registry.state(target.model_digest) is ModelLifecycleState.VALIDATED
    assert not registry.migrations
    assert registry.apply_migration(decision).source_model_digest == source.model_digest


def test_commit_failure_discards_in_memory_success_and_preserves_durable_state(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path)
    decision = _decision(registry, source, target)
    before = _stored(path)
    connection = registry._repository._connection

    class CommitFailure:
        def __init__(self, real):
            self.real = real

        def __getattr__(self, name):
            return getattr(self.real, name)

        def commit(self):
            raise sqlite3.OperationalError("injected commit failure")

    @contextmanager
    def broken_connection(**arguments):
        with connection(**arguments) as real:
            yield CommitFailure(real)

    with monkeypatch.context() as patch:
        patch.setattr(registry._repository, "_connection", broken_connection)
        with pytest.raises(ModelLifecyclePersistenceError, match="database operation failed"):
            registry.apply_migration(decision)
    assert _stored(path) == before
    assert registry.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert not registry.migrations


def test_external_sqlite_write_lock_fails_closed_without_memory_fallback(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target = _registry(path=path)
    decision = _decision(registry, source, target)
    registry._repository.timeout_seconds = 0.01
    before = _stored(path)
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ModelLifecyclePersistenceError, match="database operation failed"):
            registry.apply_migration(decision)
        connection.rollback()
    assert _stored(path) == before and not registry.migrations


def _tamper(kind, snapshot):
    if kind == "state":
        digest = snapshot["mboms"][0]["model_digest"]
        snapshot["states"][digest] = "retired"
    elif kind == "mbom_rights":
        snapshot["mboms"][0]["rights_refs"] = ["rights:forged"]
    elif kind == "training_identity":
        snapshot["mboms"][0]["training_receipt_digest"] = "f" * 64
    elif kind == "sequence":
        snapshot["history"][0]["sequence"] = 2
    elif kind == "transition":
        receipt = snapshot["history"][0]["receipt"]
        receipt["from_state"] = "active"
        receipt["receipt_digest"] = _digest(
            {key: value for key, value in receipt.items() if key != "receipt_digest"}
        )
    elif kind == "self_verifier":
        receipt = snapshot["history"][0]["receipt"]
        mbom = next(item for item in snapshot["mboms"] if item["model_digest"] == receipt["model_digest"])
        receipt["verifier_id"] = mbom["trainer_id"]
        receipt["receipt_digest"] = _digest(
            {key: value for key, value in receipt.items() if key != "receipt_digest"}
        )
    elif kind == "orphan_migration":
        snapshot["migrations"] = []
    elif kind == "orphan_rollback":
        snapshot["rollbacks"] = []
    elif kind == "decision_identity":
        snapshot["decisions"][0]["source_lifecycle_digest"] = "f" * 64
    elif kind == "caller_approval":
        snapshot["decisions"][0]["decision"]["approved"] = False
    elif kind == "evaluation":
        snapshot["decisions"][0]["evaluation"]["cases"][0]["target_output_digest"] = "f" * 64
    elif kind == "issuance_sequence":
        snapshot["decisions"][0]["issued_sequence"] = 4
    elif kind == "unknown_field":
        snapshot["promoted"] = True
    elif kind == "version":
        snapshot["schema_version"] = 2
    elif kind == "boolean_version":
        snapshot["schema_version"] = True
    elif kind == "boolean_budget":
        snapshot["budgets"]["max_models"] = True
    elif kind == "duplicate_model":
        snapshot["mboms"].append(snapshot["mboms"][0])
    elif kind == "duplicate_decision":
        snapshot["decisions"].append(snapshot["decisions"][0])
    elif kind == "duplicate_action":
        snapshot["migrations"].append(snapshot["migrations"][0])
    elif kind == "history_pair":
        snapshot["migrations"][0]["start_sequence"] = 1
    elif kind == "record_limit":
        snapshot["budgets"]["max_models"] = 1
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind",
    (
        "state",
        "mbom_rights",
        "training_identity",
        "sequence",
        "transition",
        "self_verifier",
        "orphan_migration",
        "orphan_rollback",
        "decision_identity",
        "caller_approval",
        "evaluation",
        "issuance_sequence",
        "unknown_field",
        "version",
        "boolean_version",
        "boolean_budget",
        "duplicate_model",
        "duplicate_decision",
        "duplicate_action",
        "history_pair",
        "record_limit",
    ),
)
def test_recomputed_outer_digest_cannot_hide_corrupt_evidence_graph(tmp_path, kind):
    path = tmp_path / "lifecycle.sqlite"
    registry, _, _, _, migration = _applied(path)
    _rollback(registry, migration)
    _rewrite(path, lambda snapshot: _tamper(kind, snapshot))
    corrupted = _stored(path)
    with pytest.raises(ModelLifecycleError):
        ModelLifecycleRegistry(path=path)
    with pytest.raises(ModelLifecycleError):
        _ = registry.history
    assert _stored(path) == corrupted


@pytest.mark.parametrize(
    "kind", ("mismatch", "duplicate_json", "nonfinite_json", "noncanonical_json", "oversized")
)
def test_storage_integrity_bounds_and_json_encoding_fail_closed(tmp_path, kind):
    path = tmp_path / "lifecycle.sqlite"
    registry, _, _ = _registry(path=path)
    _, snapshot, _ = _stored(path)
    if kind == "mismatch":
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("UPDATE lifecycle_state SET digest=?", ("f" * 64,))
            connection.commit()
    elif kind == "duplicate_json":
        _replace_payload(
            path, _canonical(snapshot).replace('"schema_version":1', '"schema_version":1,"schema_version":1')
        )
    elif kind == "nonfinite_json":
        _replace_payload(path, _canonical(snapshot).replace('"schema_version":1', '"schema_version":NaN'))
    elif kind == "noncanonical_json":
        _replace_payload(path, json.dumps(snapshot, indent=2))
    else:
        _replace_payload(path, " " * (MAX_SNAPSHOT_BYTES + 1))
    with pytest.raises(ModelLifecyclePersistenceError):
        ModelLifecycleRegistry(path=path)
    with pytest.raises(ModelLifecyclePersistenceError):
        _ = registry.history


def test_missing_snapshot_is_corruption_and_never_initializes_empty_state(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, _, _ = _registry(path=path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DELETE FROM lifecycle_state")
        connection.commit()
    for read in (lambda: ModelLifecycleRegistry(path=path), lambda: registry.history):
        with pytest.raises(ModelLifecyclePersistenceError, match="snapshot is missing"):
            read()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM lifecycle_state").fetchone()[0] == 0


def test_unrelated_or_unknown_database_versions_are_preserved(tmp_path):
    unrelated = tmp_path / "unrelated.sqlite"
    with closing(sqlite3.connect(unrelated)) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
        connection.execute("INSERT INTO unrelated VALUES('preserve')")
        connection.commit()
    with pytest.raises(ModelLifecyclePersistenceError, match="unrelated lifecycle database"):
        ModelLifecycleRegistry(path=unrelated)
    with closing(sqlite3.connect(unrelated)) as connection:
        assert connection.execute("SELECT value FROM unrelated").fetchone()[0] == "preserve"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    path = tmp_path / "lifecycle.sqlite"
    _registry(path=path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA user_version=2")
    with pytest.raises(ModelLifecyclePersistenceError, match="unsupported"):
        ModelLifecycleRegistry(path=path)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_extra_database_trigger_is_not_an_allowed_storage_owner(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    _registry(path=path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TRIGGER unexpected AFTER UPDATE ON lifecycle_state BEGIN SELECT 1; END")
    with pytest.raises(ModelLifecyclePersistenceError, match="schema identity is corrupt"):
        ModelLifecycleRegistry(path=path)


def test_backup_restore_retains_all_identities_without_overwriting_state(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, target, decision, migration = _applied(path)
    backup = registry.backup(tmp_path / "backup.sqlite")
    _, original_snapshot, original_digest = _stored(path)
    assert backup.snapshot_digest == original_digest
    _rollback(registry, migration)
    restored, receipt = ModelLifecycleRegistry.restore_backup(
        backup_path=backup.path, path=tmp_path / "restored.sqlite"
    )
    assert receipt.snapshot_digest == backup.snapshot_digest
    assert restored.snapshot_version == backup.snapshot_version
    assert restored.state(source.model_digest) is ModelLifecycleState.DEPRECATED
    assert restored.state(target.model_digest) is ModelLifecycleState.ACTIVE
    assert restored.apply_migration(restored.decision(decision.decision_digest)) == migration
    assert _stored(tmp_path / "restored.sqlite")[1] == original_snapshot
    _rollback(restored, restored.migrations[0])
    assert registry.state(source.model_digest) is ModelLifecycleState.ACTIVE
    assert registry.rollbacks == restored.rollbacks
    sentinel = tmp_path / "existing.sqlite"
    sentinel.write_bytes(b"preserve-existing-state")
    with pytest.raises(ModelLifecyclePersistenceError, match="already exists"):
        registry.backup(sentinel)
    with pytest.raises(ModelLifecyclePersistenceError, match="already exists"):
        ModelLifecycleRegistry.restore_backup(backup_path=backup.path, path=sentinel)
    assert sentinel.read_bytes() == b"preserve-existing-state"


def test_known_good_backup_recovers_corruption_into_new_candidate_database(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, source, _, _, _ = _applied(path)
    backup = registry.backup(tmp_path / "known-good.sqlite")
    _rewrite(path, lambda snapshot: _tamper("state", snapshot))
    corrupted = _stored(path)
    with pytest.raises(ModelLifecycleError):
        ModelLifecycleRegistry(path=path)
    restored, _ = ModelLifecycleRegistry.restore_backup(
        backup_path=backup.path, path=tmp_path / "recovered.sqlite"
    )
    assert restored.state(source.model_digest) is ModelLifecycleState.DEPRECATED
    assert _stored(path) == corrupted


def test_corrupt_and_newer_backups_never_create_restore_destination(tmp_path):
    path = tmp_path / "lifecycle.sqlite"
    registry, _, _ = _registry(path=path)
    backup = registry.backup(tmp_path / "backup.sqlite")
    _rewrite(backup.path, lambda snapshot: _tamper("version", snapshot))
    destination = tmp_path / "restored.sqlite"
    with pytest.raises(ModelLifecycleError, match="unsupported lifecycle snapshot version"):
        ModelLifecycleRegistry.restore_backup(backup_path=backup.path, path=destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".lifecycle-backup-*"))


@pytest.mark.parametrize(
    "name,value",
    (("max_models", 4097), ("max_transitions", 65537), ("max_decisions", 8193), ("max_parity_cases", 1025)),
)
def test_hard_storage_record_bounds_cannot_be_disabled(name, value):
    with pytest.raises(ModelLifecycleError, match="hard lifecycle bound"):
        ModelLifecycleRegistry(**{name: value})


def test_memory_paths_and_ambiguous_repository_arguments_are_rejected(tmp_path):
    with pytest.raises(ModelLifecyclePersistenceError, match="filesystem path"):
        ModelLifecycleRegistry(path=":memory:")
    repository = SQLiteModelLifecycleRepository(tmp_path / "repository.sqlite")
    with pytest.raises(ModelLifecycleError, match="path or repository"):
        ModelLifecycleRegistry(path=tmp_path / "other.sqlite", repository=repository)
