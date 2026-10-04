from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skeleton.ai.runtime.inference import ReferenceNGramModel
from skeleton.ai.runtime.training import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    ReferenceLocalTrainer,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    corpus_digest,
)
from skeleton.ai.runtime.training.checkpoint_archive import (
    ARCHIVE_SCHEMA,
    MAX_ARCHIVE_BYTES,
    CheckpointArchiveError,
    TrainingCheckpointArchive,
)
from skeleton.ai.runtime.training.control import WorkerLease, _canonical, _digest
from skeleton.ai.runtime.training.neural_trainer import NeuralLocalTrainer
from skeleton.storage.cas import DigestPolicy, GovernedContentStore

NOW = datetime(2026, 10, 4, 16, tzinfo=UTC)
CORPUS = ("aba", "abc", "café", "bca", "cab")


class AbruptStop(BaseException):
    pass


def _fixture(tmp_path, kind="reference"):
    datasets = DatasetRegistry(tmp_path / "datasets.sqlite3")
    ingest = IngestEnvelope.from_bytes(
        source_id="fixture://checkpoint-archive",
        payload="\n".join(CORPUS).encode(),
        parser_version="plain@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    datasets.register_ingest(ingest)
    dataset = DatasetManifest(
        dataset_id="archive-fixture",
        version="1",
        splits=(DatasetSplit("train", corpus_digest(CORPUS), len(CORPUS)),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("plain@1",),
    )
    datasets.register_dataset(dataset)
    datasets.record_quality(
        DataQualityReport.evaluate(
            dataset.digest,
            (DataQualityRule("validity", "valid_fraction", ">=", 1.0),),
            {"valid_fraction": 1.0},
        )
    )
    initial = NeuralLocalTrainer.initialize_model("archive-run", hidden_size=8, seed=13)
    manifest = TrainingRunManifest(
        run_id="archive-run",
        dataset_digest=dataset.digest,
        base_model_digest=(
            initial.model_digest if kind != "reference" else hashlib.sha256(b"empty").hexdigest()
        ),
        code_digest=hashlib.sha256(b"archive-code").hexdigest(),
        environment_digest=hashlib.sha256(b"float64-runtime").hexdigest(),
        seed=13,
        hyperparameters={},
        world_size=2 if kind == "parallel" else 1,
        parallelism="data_parallel" if kind == "parallel" else "single",
        resource_budget={"max_steps": 10000, "max_updates": 100, "max_documents": 100},
    )
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    store = GovernedContentStore(tmp_path / "cas.sqlite3")
    archive = TrainingCheckpointArchive(runs, store, tenant_id="tenant-a", trust_context="training-internal")
    return datasets, runs, store, archive, manifest


def _train(datasets, runs, manifest, kind="reference"):
    if kind == "reference":
        return ReferenceLocalTrainer(datasets, runs).train(
            manifest, CORPUS, checkpoint_every_documents=1, now=NOW
        )
    if kind == "parallel":
        from skeleton.ai.runtime.training.distributed_trainer import (
            LocalDataParallelTrainer,
        )

        return LocalDataParallelTrainer(datasets, runs).train(
            manifest, CORPUS, hidden_size=8, epochs=2, learning_rate=0.1, now=NOW
        )
    return NeuralLocalTrainer(datasets, runs).train(
        manifest, CORPUS, hidden_size=8, epochs=2, learning_rate=0.1, now=NOW
    )


def _target(tmp_path, datasets, source, manifest, store):
    target = TrainingRepository(tmp_path / "target.sqlite3")
    target.register_run(manifest, datasets, created_at=NOW)
    target.bind_execution(manifest.run_id, source.execution_binding(manifest.run_id))
    return target, TrainingCheckpointArchive(
        target, store, tenant_id="tenant-a", trust_context="training-internal"
    )


def _interrupt_after_second_update(monkeypatch, runs):
    real_checkpoint = runs.checkpoint
    calls = 0

    def interrupted(checkpoint, lease, **kwargs):
        nonlocal calls
        digest = real_checkpoint(checkpoint, lease, **kwargs)
        calls += 1
        if calls == 3:
            raise AbruptStop("after committed second update")
        return digest

    monkeypatch.setattr(runs, "checkpoint", interrupted)


def _lease(runs, run_id):
    return WorkerLease(
        **json.loads(
            runs._db.execute("SELECT lease_json FROM worker_lease WHERE run_id=?", (run_id,)).fetchone()[0]
        )
    )


@pytest.mark.parametrize("kind", ["reference", "neural", "parallel"])
def test_full_state_backup_restart_import_and_resume_equivalence(tmp_path, monkeypatch, kind):
    datasets, runs, store, archive, manifest = _fixture(tmp_path, kind)
    _interrupt_after_second_update(monkeypatch, runs)
    with pytest.raises(AbruptStop):
        _train(datasets, runs, manifest, kind)
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    old_lease = _lease(runs, manifest.run_id)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    payload = runs.checkpoint_payload(checkpoint)
    assert payload["model"] is not None
    assert receipt.payload_digest == checkpoint.payload_digest
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    target.close()
    store.close()
    runs.close()
    reopened_store = GovernedContentStore(tmp_path / "cas.sqlite3")
    reopened = TrainingRepository(tmp_path / "target.sqlite3")
    importing = TrainingCheckpointArchive(
        reopened, reopened_store, tenant_id="tenant-a", trust_context="training-internal"
    )
    verified = importing.verify_backup(receipt, datasets, CORPUS)
    assert verified.manifest == manifest
    assert verified.checkpoint == checkpoint
    assert verified.payload == payload
    assert reopened.latest_checkpoint(manifest.run_id) is None
    assert reopened.state(manifest.run_id) == "registered"
    assert importing.restore(receipt, datasets, CORPUS) == checkpoint
    epoch = reopened._epoch(manifest.run_id)
    assert importing.restore(receipt, datasets, CORPUS) == checkpoint
    assert reopened._epoch(manifest.run_id) == epoch
    assert reopened.state(manifest.run_id) == "recovering"
    assert reopened.checkpoint_payload(checkpoint) == payload
    reopened.start(manifest.run_id)
    with pytest.raises(TrainingStateError, match="stale"):
        reopened.assert_worker_current(old_lease)
    reopened.recover(manifest.run_id)
    model, artifact = _train(datasets, reopened, manifest, kind)
    if kind == "reference":
        expected = ReferenceNGramModel.train(CORPUS, order=2, model_id=model.model_id)
    elif kind == "parallel":
        expected, _expected_artifact = _train(
            datasets, TrainingRepository(tmp_path / "baseline.sqlite3"), manifest, kind
        )
    else:
        expected = NeuralLocalTrainer.initialize_model(manifest.run_id, hidden_size=8, seed=13)
        expected.train(CORPUS, epochs=2, learning_rate=0.1)
    assert artifact.model_digest == expected.model_digest == model.model_digest
    assert reopened.state(manifest.run_id) == "completed"


def test_backup_is_idempotent_and_survives_digest_alias_migration(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    assert archive.backup(manifest.run_id, datasets, CORPUS) == receipt
    assert archive.receipts(manifest.run_id) == (receipt,)
    store.digest_policy = DigestPolicy(current_algorithm="sha256", accepted_algorithms=("sha256", "sha512"))
    store.migrate_digest(
        tenant_id=receipt.tenant_id, logical_id=receipt.logical_id, version=1, to_algorithm="sha512"
    )
    assert archive.backup(manifest.run_id, datasets, CORPUS) == receipt
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    importing.restore(receipt, datasets, CORPUS)
    assert target.latest_checkpoint(manifest.run_id).digest == receipt.checkpoint_digest


def test_retention_preserves_latest_pins_unbacked_and_backup_receipts(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoints = runs.checkpoints(manifest.run_id)
    for checkpoint in checkpoints:
        if checkpoint == checkpoints[2]:
            continue
        archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoint.digest)
    archive.pin(manifest.run_id, checkpoints[-1].digest, "recovery-start", kind="recovery")
    archive.pin(manifest.run_id, checkpoints[-2].digest, "active-reader", kind="active")
    removed = archive.retain(manifest.run_id, keep_newest=1)
    kept = {item.digest for item in runs.checkpoints(manifest.run_id)}
    assert kept == {
        item.digest for item in (checkpoints[0], checkpoints[2], checkpoints[-1], checkpoints[-2])
    }
    assert len(removed) == 2
    assert len(archive.receipts(manifest.run_id)) == len(checkpoints) - 1
    assert store.get(tenant_id="tenant-a", logical_id=f"training-checkpoint:{removed[0]}", version=1)[1]
    archive.unpin(manifest.run_id, "active-reader")
    assert archive.retain(manifest.run_id, keep_newest=1) == (checkpoints[-2].digest,)


def test_running_pins_require_current_lease_and_keep_active_reference(tmp_path, monkeypatch):
    datasets, runs, _store, archive, manifest = _fixture(tmp_path)
    _interrupt_after_second_update(monkeypatch, runs)
    with pytest.raises(AbruptStop):
        _train(datasets, runs, manifest)
    checkpoint = runs.checkpoints(manifest.run_id)[-1]
    lease = _lease(runs, manifest.run_id)
    with pytest.raises(CheckpointArchiveError, match="worker lease"):
        archive.pin(manifest.run_id, checkpoint.digest, "active-reader", kind="active")
    archive.pin(manifest.run_id, checkpoint.digest, "active-reader", kind="active", lease=lease)
    with pytest.raises(CheckpointArchiveError, match="worker lease"):
        archive.unpin(manifest.run_id, "active-reader")
    for item in runs.checkpoints(manifest.run_id):
        archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=item.digest)
    runs.recover(manifest.run_id)
    runs.start(manifest.run_id)
    with pytest.raises(TrainingStateError, match="stale"):
        archive.unpin(manifest.run_id, "active-reader", lease=lease)
    archive.retain(manifest.run_id, keep_newest=1)
    assert checkpoint in runs.checkpoints(manifest.run_id)


def test_backup_receipt_failure_leaves_no_authoritative_partial_backup_and_retries(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    runs._db.execute(
        "CREATE TEMP TRIGGER reject_backup BEFORE INSERT ON training_checkpoint_archive BEGIN SELECT RAISE(ABORT,'receipt failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="receipt failure"):
        archive.backup(manifest.run_id, datasets, CORPUS)
    assert archive.receipts(manifest.run_id) == ()
    checkpoint = runs.latest_checkpoint(manifest.run_id)
    assert store.get(tenant_id="tenant-a", logical_id=f"training-checkpoint:{checkpoint.digest}", version=1)[
        1
    ]
    runs._db.execute("DROP TRIGGER reject_backup")
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    assert receipt.checkpoint_digest == checkpoint.digest


def test_import_payload_failure_rolls_back_metadata_fence_and_receipt(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    target._db.execute(
        "CREATE TEMP TRIGGER reject_import BEFORE INSERT ON training_checkpoint_payload BEGIN SELECT RAISE(ABORT,'payload failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="payload failure"):
        importing.restore(receipt, datasets, CORPUS)
    assert target.latest_checkpoint(manifest.run_id) is None
    assert target.state(manifest.run_id) == "registered"
    assert target._epoch(manifest.run_id) == 0
    assert importing.receipts(manifest.run_id) == ()
    assert target._db.execute("SELECT COUNT(*) FROM training_checkpoint_reference").fetchone()[0] == 0
    target._db.execute("DROP TRIGGER reject_import")
    importing.restore(receipt, datasets, CORPUS)


def test_retention_failure_rolls_back_deleted_payloads_and_checkpoints(tmp_path):
    datasets, runs, _store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoints = runs.checkpoints(manifest.run_id)
    for checkpoint in checkpoints:
        archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoint.digest)
    runs._db.execute(
        "CREATE TEMP TRIGGER reject_retention BEFORE DELETE ON training_checkpoint BEGIN SELECT RAISE(ABORT,'retention failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="retention failure"):
        archive.retain(manifest.run_id, keep_newest=1)
    assert runs.checkpoints(manifest.run_id) == checkpoints
    for checkpoint in checkpoints:
        assert runs.checkpoint_payload(checkpoint)


@pytest.mark.parametrize("corruption", ["bytes", "missing", "address", "receipt"])
def test_corrupt_backups_block_import_and_retention_without_mutation(tmp_path, corruption):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoints = runs.checkpoints(manifest.run_id)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoints[-1].digest)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    if corruption == "bytes":
        store._db.execute("UPDATE governed_object SET payload=?", (b"{}",))
        store._db.commit()
    elif corruption == "missing":
        store._db.execute("DELETE FROM governed_digest")
        store._db.execute("DELETE FROM governed_object")
        store._db.commit()
    elif corruption == "address":
        store._db.execute("UPDATE governed_digest SET digest=?", ("0" * 64,))
        store._db.commit()
    else:
        receipt = replace(receipt, payload_digest="0" * 64)
        runs._db.execute(
            "UPDATE training_checkpoint_archive SET receipt_json=?,receipt_digest=?",
            (_canonical(receipt.as_dict()), receipt.digest),
        )
        runs._db.commit()
    with pytest.raises(CheckpointArchiveError):
        importing.restore(receipt, datasets, CORPUS)
    with pytest.raises(CheckpointArchiveError):
        archive.retain(manifest.run_id, keep_newest=1)
    assert target.latest_checkpoint(manifest.run_id) is None
    assert target._epoch(manifest.run_id) == 0
    assert runs.checkpoints(manifest.run_id) == checkpoints


@pytest.mark.parametrize("field", ["code_digest", "environment_digest", "base_model_digest", "seed"])
def test_restore_rejects_exact_manifest_compatibility_drift(tmp_path, field):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    replacement = replace(manifest, **{field: 42 if field == "seed" else "f" * 64})
    target = TrainingRepository(tmp_path / "target.sqlite3")
    target.register_run(replacement, datasets)
    binding = dict(runs.execution_binding(manifest.run_id), manifest_digest=replacement.digest)
    target.bind_execution(replacement.run_id, binding)
    importing = TrainingCheckpointArchive(
        target, store, tenant_id="tenant-a", trust_context="training-internal"
    )
    with pytest.raises(CheckpointArchiveError, match="manifest/code/environment"):
        importing.restore(receipt, datasets, CORPUS)
    assert target.latest_checkpoint(manifest.run_id) is None


@pytest.mark.parametrize("substitution", ["tenant", "trust", "binding", "corpus"])
def test_restore_rejects_cross_boundary_substitution(tmp_path, substitution):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    corpus = CORPUS
    if substitution == "tenant":
        importing = TrainingCheckpointArchive(
            target, store, tenant_id="tenant-b", trust_context="training-internal"
        )
    elif substitution == "trust":
        importing = TrainingCheckpointArchive(target, store, tenant_id="tenant-a", trust_context="public")
    elif substitution == "binding":
        binding = dict(target.execution_binding(manifest.run_id), split_name="alternate")
        target._db.execute(
            "UPDATE training_execution_binding SET binding_json=?,binding_digest=?",
            (_canonical(binding), _digest(binding)),
        )
        target._db.commit()
    else:
        corpus = tuple(reversed(CORPUS))
    with pytest.raises((CheckpointArchiveError, ValueError)):
        importing.restore(receipt, datasets, corpus)
    assert target.latest_checkpoint(manifest.run_id) is None


def test_restore_rejects_rollback_and_keeps_completed_target_idempotent(tmp_path):
    datasets, runs, _store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoints = runs.checkpoints(manifest.run_id)
    oldest = archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoints[-1].digest)
    latest = archive.backup(manifest.run_id, datasets, CORPUS)
    with pytest.raises(CheckpointArchiveError, match="rewind"):
        archive.restore(oldest, datasets, CORPUS)
    epoch = runs._epoch(manifest.run_id)
    assert archive.restore(latest, datasets, CORPUS) == checkpoints[0]
    assert runs.state(manifest.run_id) == "completed"
    assert runs._epoch(manifest.run_id) == epoch


@pytest.mark.parametrize("count", [0, -1, True, 1025, 1.5])
def test_retention_count_is_bounded(tmp_path, count):
    _datasets, _runs, _store, archive, manifest = _fixture(tmp_path)
    with pytest.raises(ValueError, match="retained checkpoint count"):
        archive.retain(manifest.run_id, keep_newest=count)


def test_envelope_requires_canonical_supported_bounded_state(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    data = store.get(tenant_id=receipt.tenant_id, logical_id=receipt.logical_id, version=1)[1]
    value = json.loads(data)
    assert value["schema_version"] == ARCHIVE_SCHEMA
    assert "corpus" not in value
    malformed = dict(value, schema_version="unknown")
    for candidate in (
        json.dumps(value).encode(),
        _canonical(malformed).encode(),
        b" " * (MAX_ARCHIVE_BYTES + 1),
    ):
        with pytest.raises(CheckpointArchiveError, match="envelope"):
            archive._decode(candidate)
    value["payload"]["model"] = None
    value["checkpoint"]["payload_digest"] = _digest(value["payload"])
    with pytest.raises(CheckpointArchiveError, match="compatibility"):
        archive._validate_model(
            datasets,
            manifest,
            value["binding"],
            replace(runs.latest_checkpoint(manifest.run_id), payload_digest=_digest(value["payload"])),
            value["payload"],
            CORPUS,
        )


def test_reference_backup_does_not_require_optional_numpy(tmp_path):
    datasets, runs, store, _archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    datasets.close()
    runs.close()
    store.close()
    program = """
import builtins, json, sys
original = builtins.__import__
def without_numpy(name, *args, **kwargs):
    if name == 'numpy' or name.startswith('numpy.'):
        raise ImportError('optional numpy is deliberately absent')
    return original(name, *args, **kwargs)
builtins.__import__ = without_numpy
from skeleton.ai.runtime.training.control import TrainingRepository
from skeleton.ai.runtime.training.data import DatasetRegistry
from skeleton.ai.runtime.training.checkpoint_archive import TrainingCheckpointArchive
from skeleton.storage.cas import GovernedContentStore
from pathlib import Path
path = Path(sys.argv[1])
runs = TrainingRepository(path / 'runs.sqlite3')
datasets = DatasetRegistry(path / 'datasets.sqlite3')
store = GovernedContentStore(path / 'cas.sqlite3')
archive = TrainingCheckpointArchive(runs, store, tenant_id='tenant-a', trust_context='training-internal')
receipt = archive.backup('archive-run', datasets, json.loads(sys.argv[2]))
assert receipt.payload_schema == 'skeleton.reference_training_resume.v1'
assert 'numpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path), json.dumps(CORPUS)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mutation", ["revoke", "delete", "epoch"])
def test_current_dataset_authority_is_required_before_backup_and_import(tmp_path, mutation):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    if mutation == "revoke":
        source = datasets.require_training_ready(manifest.dataset_digest).source_ingest_digests[0]
        datasets.revoke_source_rights(source, reason="rights withdrawn", command_id="archive-revoke")
    elif mutation == "delete":
        datasets.delete_dataset(
            manifest.dataset_digest, reason="retention expired", command_id="archive-delete"
        )
    else:
        datasets._db.execute("UPDATE dataset_authority SET epoch=epoch+1")
        datasets._db.commit()
    with pytest.raises((ValueError, PermissionError, CheckpointArchiveError)):
        archive.backup(manifest.run_id, datasets, CORPUS)
    with pytest.raises((ValueError, PermissionError, CheckpointArchiveError)):
        importing.restore(receipt, datasets, CORPUS)
    assert target.latest_checkpoint(manifest.run_id) is None
    assert target.state(manifest.run_id) == "registered"


def test_self_consistent_digest_cannot_bypass_full_model_validation(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    original = archive.backup(manifest.run_id, datasets, CORPUS)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    data = store.get(tenant_id=original.tenant_id, logical_id=original.logical_id, version=1)[1]
    value = json.loads(data)
    # Produce an independently addressed, digest-consistent envelope containing
    # an invalid full model. Import must perform semantic validation before SQL.
    value["payload"]["model"] = None
    value["checkpoint"]["payload_digest"] = _digest(value["payload"])
    from skeleton.ai.runtime.training.control import TrainingCheckpoint

    checkpoint = TrainingCheckpoint.from_dict(value["checkpoint"])
    data = _canonical(value).encode()
    addressed = store.put(
        tenant_id="tenant-a",
        logical_id=f"training-checkpoint:{checkpoint.digest}",
        version=1,
        trust_context="training-internal",
        payload=data,
    )
    invalid = archive._make_receipt(addressed, data, manifest, value["binding"], checkpoint, value["payload"])
    with pytest.raises(CheckpointArchiveError):
        importing.restore(invalid, datasets, CORPUS)
    assert target.latest_checkpoint(manifest.run_id) is None
    assert target._epoch(manifest.run_id) == 0


def test_imported_recovery_reference_survives_newer_checkpoint_retention(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    older = runs.checkpoints(manifest.run_id)[-2]
    receipt = archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=older.digest)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    importing.restore(receipt, datasets, CORPUS)
    _train(datasets, target, manifest)
    for checkpoint in target.checkpoints(manifest.run_id):
        importing.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoint.digest)
    importing.retain(manifest.run_id, keep_newest=1)
    assert target.checkpoints(manifest.run_id) == (target.latest_checkpoint(manifest.run_id), older)


def test_committed_receipt_without_published_proof_is_repairable_by_exact_backup_retry(tmp_path, monkeypatch):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    publish = archive._publish_commit

    def crash(receipt):
        raise AbruptStop("before commit proof publication")

    monkeypatch.setattr(archive, "_publish_commit", crash)
    with pytest.raises(AbruptStop):
        archive.backup(manifest.run_id, datasets, CORPUS)
    receipt = archive.receipts(manifest.run_id)[0]
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    with pytest.raises(CheckpointArchiveError):
        importing.restore(receipt, datasets, CORPUS)
    assert target.latest_checkpoint(manifest.run_id) is None
    monkeypatch.setattr(archive, "_publish_commit", publish)
    assert archive.backup(manifest.run_id, datasets, CORPUS) == receipt
    importing.restore(receipt, datasets, CORPUS)


def test_valid_changed_model_with_self_consistent_digests_has_no_issued_backup_authority(tmp_path):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    receipt = archive.backup(manifest.run_id, datasets, CORPUS)
    original = store.get(tenant_id=receipt.tenant_id, logical_id=receipt.logical_id, version=1)[1]
    value = json.loads(original)
    changed = ReferenceNGramModel.train(
        ("different valid model",), order=2, model_id=value["payload"]["model"]["model_id"]
    )
    value["payload"]["model"] = changed.to_dict()
    value["checkpoint"]["model_digest"] = changed.model_digest
    value["checkpoint"]["payload_digest"] = _digest(value["payload"])
    from skeleton.ai.runtime.training.control import TrainingCheckpoint

    checkpoint = TrainingCheckpoint.from_dict(value["checkpoint"])
    data = _canonical(value).encode()
    addressed = store.put(
        tenant_id="tenant-a",
        logical_id=f"training-checkpoint:{checkpoint.digest}",
        version=1,
        trust_context="training-internal",
        payload=data,
    )
    forged = archive._make_receipt(addressed, data, manifest, value["binding"], checkpoint, value["payload"])
    archive._validate_model(datasets, manifest, value["binding"], checkpoint, value["payload"], CORPUS)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    with pytest.raises(CheckpointArchiveError):
        importing.restore(forged, datasets, CORPUS)
    with pytest.raises(CheckpointArchiveError, match="committed backup receipt"):
        archive._publish_commit(forged)
    assert target.latest_checkpoint(manifest.run_id) is None


def _cli_archive_fixture(tmp_path):
    from skeleton.ai.runtime.training.cli import build_governed_artifact

    path = tmp_path / "licensed.txt"
    path.write_text("archive cli exact identity", encoding="utf-8")
    request = {
        "corpus_paths": (path,),
        "state_directory": tmp_path / "state",
        "output_path": tmp_path / "model.json",
        "run_id": "cli-archive",
        "dataset_id": "cli-archive-data",
        "rights_refs": ("license:fixture",),
        "algorithm": "reference",
    }
    build_governed_artifact(**request)
    datasets = DatasetRegistry(tmp_path / "state" / "datasets.sqlite3")
    runs = TrainingRepository(tmp_path / "state" / "training.sqlite3")
    store = GovernedContentStore(tmp_path / "cas.sqlite3")
    archive = TrainingCheckpointArchive(runs, store, tenant_id="tenant-a", trust_context="training-internal")
    manifest = runs.manifest("cli-archive")
    corpus = datasets.training_corpus(manifest.dataset_digest)
    return datasets, runs, store, archive, manifest, corpus


@pytest.mark.parametrize("field", ["request_digest", "acquired_at", "dataset_version", "source", "rights"])
def test_corrupt_cli_admission_snapshot_is_not_backed_up(tmp_path, field):
    datasets, runs, store, archive, manifest, corpus = _cli_archive_fixture(tmp_path)
    if field in {"source", "rights"}:
        request = json.loads(runs._db.execute("SELECT request_json FROM governed_cli_request").fetchone()[0])
        if field == "source":
            request["sources"][0]["path"] = str(tmp_path / "substituted.txt")
        else:
            request["rights_refs"] = ["license:other"]
        runs._db.execute(
            "UPDATE governed_cli_request SET request_json=?, request_digest=?",
            (_canonical(request), _digest(request)),
        )
    else:
        replacement = "0" * 64 if field == "request_digest" else "not-utc" if field == "acquired_at" else 20
        runs._db.execute(f"UPDATE governed_cli_request SET {field}=?", (replacement,))
    runs._db.commit()
    with pytest.raises(CheckpointArchiveError):
        archive.backup(manifest.run_id, datasets, corpus)
    assert archive.receipts(manifest.run_id) == ()
    assert store._db.execute("SELECT COUNT(*) FROM governed_object").fetchone()[0] == 0


def test_cli_destination_conflict_rolls_back_entire_checkpoint_import(tmp_path):
    datasets, runs, store, archive, manifest, corpus = _cli_archive_fixture(tmp_path)
    receipt = archive.backup(manifest.run_id, datasets, corpus)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    row = runs._db.execute("SELECT * FROM governed_cli_request").fetchone()
    target._db.execute(
        "CREATE TABLE governed_cli_request(run_id TEXT PRIMARY KEY,request_digest TEXT,request_json TEXT,acquired_at TEXT,dataset_version INTEGER)"
    )
    target._db.execute(
        "INSERT INTO governed_cli_request VALUES (?,?,?,?,?)", (*row[:3], "2020-01-01T00:00:00+00:00", row[4])
    )
    target._db.commit()
    with pytest.raises(CheckpointArchiveError, match="conflicts with admitted"):
        importing.restore(receipt, datasets, corpus)
    assert target.latest_checkpoint(manifest.run_id) is None
    assert target._epoch(manifest.run_id) == 0
    assert target._db.execute("SELECT acquired_at FROM governed_cli_request").fetchone()[0].startswith("2020")


@pytest.mark.parametrize("corruption", ["bytes", "trust"])
def test_corrupt_committed_proof_fails_before_import_or_retention(tmp_path, corruption):
    datasets, runs, store, archive, manifest = _fixture(tmp_path)
    _train(datasets, runs, manifest)
    checkpoint = runs.checkpoints(manifest.run_id)[-1]
    receipt = archive.backup(manifest.run_id, datasets, CORPUS, checkpoint_digest=checkpoint.digest)
    target, importing = _target(tmp_path, datasets, runs, manifest, store)
    logical_id = f"training-checkpoint-commit:{checkpoint.digest}"
    if corruption == "bytes":
        store._db.execute("UPDATE governed_object SET payload=? WHERE logical_id=?", (b"{}", logical_id))
    else:
        store._db.execute(
            "UPDATE governed_object SET trust_context=? WHERE logical_id=?", ("public", logical_id)
        )
    store._db.commit()
    with pytest.raises(CheckpointArchiveError):
        importing.restore(receipt, datasets, CORPUS)
    with pytest.raises(CheckpointArchiveError):
        archive.retain(manifest.run_id, keep_newest=1)
    assert target.latest_checkpoint(manifest.run_id) is None
    assert checkpoint in runs.checkpoints(manifest.run_id)
