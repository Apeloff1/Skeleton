from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from skeleton.ai.runtime.learning_foundation.multimodal import (
    LearningModality,
    MultimodalCorpus,
)
from skeleton.ai.runtime.training.control import TrainingRepository, TrainingRunManifest
from skeleton.ai.runtime.training.data import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    MaterializedTrainingSource,
    document_sequence_digest,
)
from skeleton.ai.runtime.training.trainer import ReferenceLocalTrainer

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _source(
    documents=("alpha beta gamma", "beta gamma delta"),
    *,
    rights=("training",),
    classification="internal",
    source_id="fixture://actual-source",
):
    payload = json.dumps(list(documents), ensure_ascii=False, separators=(",", ":")).encode()
    envelope = IngestEnvelope.from_bytes(
        source_id=source_id,
        payload=payload,
        parser_version="json-documents@1",
        classification=classification,
        rights=rights,
        trusted=True,
        acquired_at=NOW,
    )
    return MaterializedTrainingSource(
        envelope=envelope,
        payload=payload,
        format="json_documents",
        rights_refs=("rights:fixture-consent",),
        lineage_refs=("source:actual-fixture",),
        evidence={"acquisition": "fixture-bytes"},
    )


def _ingest(registry, source=None, **overrides):
    arguments = {
        "ingestion_id": "ingest-v1",
        "dataset_id": "governed-data",
        "expected_version": 0,
        "sources": {"train": (source or _source(),)},
        "classification": "internal",
        "permitted_uses": ("training",),
        "retention_class": "model-development",
    }
    arguments.update(overrides)
    return registry.ingest_materialized(**arguments)


def _run_manifest(dataset, run_id="governed-run"):
    return TrainingRunManifest(
        run_id=run_id,
        dataset_digest=dataset.digest,
        base_model_digest=_digest("reference-ngram"),
        code_digest=_digest("test-code"),
        environment_digest=_digest("test-python"),
        hyperparameters={"order": 2},
        seed=7,
        resource_budget={"max_documents": 10, "max_steps": 100, "max_corpus_bytes": 4096},
    )


def _counts(registry):
    tables = (
        "ingest_envelope",
        "dataset_manifest",
        "quality_report",
        "materialized_source",
        "materialized_document",
        "materialized_ingestion",
        "source_authority",
        "dataset_authority",
    )
    return tuple(registry._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables)


def test_materialized_bytes_survive_restart_and_feed_real_native_training(tmp_path):
    path = tmp_path / "datasets.sqlite3"
    registry = DatasetRegistry(path)
    source = _source()
    receipt = _ingest(registry, source)
    corpus = registry.training_corpus(receipt.dataset_digest)
    assert corpus == source.documents()
    assert receipt.manifest.materialization_digest is not None
    assert registry.latest_quality(receipt.dataset_digest).observation_digest == receipt.observation_digest
    registry.close()
    registry = DatasetRegistry(path)
    restored = registry.materialized_ingestion(receipt.ingestion_id)
    assert restored.digest == receipt.digest
    assert registry.materialized_sources(receipt.dataset_digest)[0].as_dict() == source.as_dict()
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    model, artifact = ReferenceLocalTrainer(registry, runs).train(
        _run_manifest(receipt.manifest),
        registry.training_corpus(receipt.dataset_digest),
        checkpoint_every_documents=1,
        now=NOW,
    )
    assert artifact.document_count == 2
    learned_digest = model.model_digest
    runs.close()
    registry.close()
    registry = DatasetRegistry(path)
    runs = TrainingRepository(tmp_path / "runs.sqlite3")
    restored_model, restored_artifact = ReferenceLocalTrainer(registry, runs).load_artifact("governed-run")
    assert restored_model.model_digest == learned_digest
    assert restored_artifact == artifact
    assert registry.training_corpus(receipt.dataset_digest) == source.documents()


def test_materialized_sequence_defends_newline_join_alias_before_training_mutation(tmp_path):
    original = ("a\nb", "c")
    alias = ("a", "b\nc")
    assert _digest("\n".join(original)) == _digest("\n".join(alias))
    assert document_sequence_digest(original) != document_sequence_digest(alias)
    registry = DatasetRegistry()
    receipt = _ingest(registry, _source(original))
    with pytest.raises(ValueError, match="exact document sequence"):
        registry.validate_training_corpus(receipt.dataset_digest, alias)
    runs = TrainingRepository()
    with pytest.raises(ValueError, match="exact document sequence"):
        ReferenceLocalTrainer(registry, runs).train(_run_manifest(receipt.manifest), alias, now=NOW)
    with pytest.raises(KeyError):
        runs.manifest("governed-run")


def test_declared_legacy_split_does_not_invent_materialized_bytes():
    registry = DatasetRegistry()
    source = _source()
    registry.register_ingest(source.envelope)
    manifest = DatasetManifest(
        "legacy",
        "1",
        (DatasetSplit("train", _digest("declared-only"), 2),),
        (source.envelope.content_digest,),
        "internal",
        ("training",),
        "model-development",
        (source.envelope.parser_version,),
    )
    registry.register_dataset(manifest)
    registry.record_quality(
        DataQualityReport.evaluate(
            manifest.digest, (DataQualityRule("legacy", "valid_fraction", ">=", 1),), {"valid_fraction": 1.0}
        )
    )
    assert registry.require_training_ready(manifest.digest) == manifest
    with pytest.raises(RuntimeError, match="no materialized corpus bytes"):
        registry.training_corpus(manifest.digest)


def test_exact_ingestion_replay_returns_original_version_after_later_commit():
    registry = DatasetRegistry()
    first_source = _source()
    first = _ingest(registry, first_source)
    second = _ingest(
        registry,
        _source(("new actual documents",), source_id="fixture://second"),
        ingestion_id="ingest-v2",
        expected_version=1,
    )
    assert second.manifest.version == "2"
    assert _ingest(registry, first_source).digest == first.digest
    assert registry.materialized_ingestion("ingest-v1").manifest.version == "1"
    assert registry.training_corpus(first.dataset_digest) == first_source.documents()


@pytest.mark.parametrize(
    "override",
    (
        {"expected_version": 1},
        {"retention_class": "different-retention"},
        {"classification": "restricted"},
    ),
)
def test_changed_ingestion_identity_is_rejected_without_commit(override):
    registry = DatasetRegistry()
    _ingest(registry)
    before = _counts(registry)
    with pytest.raises(ValueError, match="different request"):
        _ingest(registry, **override)
    assert _counts(registry) == before


@pytest.mark.parametrize(
    "changes",
    (
        {"expected_version": 1},
        {"quality_rules": (DataQualityRule("expected-validation", "validation.record_count", ">=", 1),)},
        {"quality_rules": (DataQualityRule("observed.records", "record_count", ">=", 0),)},
        {"sources": {"train": (_source(rights=("evaluation",)),)}},
        {"classification": "public"},
    ),
)
def test_rejected_ingestion_commits_neither_bytes_nor_authority(changes):
    registry = DatasetRegistry()
    before = _counts(registry)
    with pytest.raises((ValueError, RuntimeError, PermissionError)):
        _ingest(registry, **changes)
    assert _counts(registry) == before


@pytest.mark.parametrize(
    "payload", (b"\xff", b"[]", b'[["nested"]]', b"[true]", b'[" "]', b'{"documents":["text"]}')
)
def test_unparseable_or_invalid_source_bytes_never_commit(payload):
    registry = DatasetRegistry()
    envelope = IngestEnvelope.from_bytes(
        source_id="fixture:bad",
        payload=payload,
        parser_version="json-documents@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    with pytest.raises(ValueError):
        MaterializedTrainingSource(envelope, payload, "json_documents", ("rights:fixture",))
    assert _counts(registry) == (0,) * 8


def test_materialized_quality_rejects_fabricated_metrics_and_wrong_split_observations():
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    report = registry.latest_quality(receipt.dataset_digest)
    with pytest.raises(ValueError, match="does not bind materialized"):
        registry.record_quality(replace(report, metrics={**report.metrics, "text_bytes": 0.0}))
    with pytest.raises(ValueError, match="does not bind materialized"):
        registry.record_quality(
            replace(report, split_sequence_digests={"train": _digest("another-sequence")})
        )
    with pytest.raises(ValueError, match="does not bind materialized"):
        registry.record_quality(
            DataQualityReport.evaluate(
                receipt.dataset_digest, (DataQualityRule("declared", "score", ">=", 1),), {"score": 1.0}
            )
        )


def test_materialized_quality_cannot_remove_mandatory_baseline_rules():
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    report = registry.latest_quality(receipt.dataset_digest)
    forged = DataQualityReport.evaluate(
        receipt.dataset_digest,
        (DataQualityRule("weak", "record_count", ">=", 0, critical=False),),
        report.metrics,
        observation_digest=report.observation_digest,
        split_sequence_digests=report.split_sequence_digests,
    )
    with pytest.raises(ValueError, match="bypass observed baseline"):
        registry.record_quality(forged)


@pytest.mark.parametrize(
    "table,column,where",
    (
        ("materialized_source", "payload", "1=1"),
        ("materialized_document", "document_bytes", "ordinal=0"),
        ("materialized_dataset", "observation_json", "1=1"),
    ),
)
def test_persisted_content_or_observation_tampering_fails_closed(table, column, where):
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    registry._db.execute(
        f"UPDATE {table} SET {column}=? WHERE {where}",
        (b"tampered" if column != "observation_json" else "{}",),
    )
    registry._db.commit()
    with pytest.raises((ValueError, RuntimeError)):
        registry.training_corpus(receipt.dataset_digest)


def test_missing_raw_bytes_cannot_fall_back_to_remaining_document_projection():
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    registry._db.execute("DELETE FROM materialized_source")
    registry._db.commit()
    with pytest.raises(RuntimeError, match="source bytes unavailable"):
        registry.training_corpus(receipt.dataset_digest)


@pytest.mark.parametrize("operation", ("revoke", "delete_source", "delete_dataset"))
def test_lifecycle_is_restart_safe_and_blocks_export_training_and_replay(tmp_path, operation):
    path = tmp_path / "dataset.sqlite3"
    registry = DatasetRegistry(path)
    source = _source()
    receipt = _ingest(registry, source)
    epoch = registry.dataset_authority_epoch(receipt.dataset_digest)
    if operation == "revoke":
        event = registry.revoke_source_rights(
            source.envelope.content_digest, reason="consent withdrawn", command_id="lifecycle-command"
        )
        assert (
            registry.revoke_source_rights(
                source.envelope.content_digest, reason="consent withdrawn", command_id="lifecycle-command"
            )
            == event
        )
    elif operation == "delete_source":
        registry.delete_source(
            source.envelope.content_digest, reason="source deletion", command_id="lifecycle-command"
        )
        assert registry._db.execute("SELECT COUNT(*) FROM materialized_source").fetchone()[0] == 0
    else:
        registry.delete_dataset(
            receipt.dataset_digest, reason="dataset deletion", command_id="lifecycle-command"
        )
        assert registry._db.execute("SELECT COUNT(*) FROM materialized_document").fetchone()[0] == 0
    assert registry.dataset_authority_epoch(receipt.dataset_digest) > epoch
    registry.close()
    registry = DatasetRegistry(path)
    for action in (
        lambda: registry.training_corpus(receipt.dataset_digest),
        lambda: registry.validate_training_corpus(receipt.dataset_digest, source.documents()),
        lambda: registry.assert_dataset_authority(receipt.dataset_digest, epoch),
        lambda: registry.materialized_ingestion(receipt.ingestion_id),
        lambda: _ingest(registry, source),
    ):
        with pytest.raises(PermissionError):
            action()
    runs = TrainingRepository()
    with pytest.raises(PermissionError):
        ReferenceLocalTrainer(registry, runs).train(_run_manifest(receipt.manifest), source.documents())
    with pytest.raises(KeyError):
        runs.manifest("governed-run")


def test_revoked_source_cannot_be_laundered_under_new_dataset_identity():
    registry = DatasetRegistry()
    source = _source()
    _ingest(registry, source)
    registry.revoke_source_rights(source.envelope.content_digest, reason="withdrawn", command_id="revoke")
    before = _counts(registry)
    with pytest.raises(PermissionError, match="rights revoked"):
        _ingest(registry, source, dataset_id="new-identity", ingestion_id="new-ingestion")
    assert _counts(registry) == before


def test_durable_epoch_reset_or_deleted_status_cannot_erase_revocation():
    registry = DatasetRegistry()
    source = _source()
    receipt = _ingest(registry, source)
    registry.revoke_source_rights(source.envelope.content_digest, reason="withdrawn", command_id="revoke")
    registry._db.execute("UPDATE source_authority SET epoch=0,revoked_uses_json='[]'")
    registry._db.commit()
    with pytest.raises(ValueError, match="lifecycle evidence mismatch"):
        registry.require_training_ready(receipt.dataset_digest)


def test_quality_policy_change_fences_inflight_training_and_cannot_reorder_old_pass():
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    epoch = registry.dataset_authority_epoch(receipt.dataset_digest)
    initial = registry.latest_quality(receipt.dataset_digest)
    stronger = DataQualityReport.evaluate(
        receipt.dataset_digest,
        (*initial.rules, DataQualityRule("more-data", "record_count", ">=", 3)),
        initial.metrics,
        observation_digest=initial.observation_digest,
        split_sequence_digests=initial.split_sequence_digests,
    )
    registry.record_quality(stronger)
    with pytest.raises(PermissionError, match="epoch changed"):
        registry.assert_dataset_authority(receipt.dataset_digest, epoch)
    with pytest.raises(RuntimeError, match="critical quality"):
        registry.require_training_ready(receipt.dataset_digest)
    registry.record_quality(initial)
    assert registry.latest_quality(receipt.dataset_digest).digest == stronger.digest


def test_authority_guard_orders_concurrent_revocation_after_protected_commit(tmp_path):
    path = tmp_path / "dataset.sqlite3"
    registry = DatasetRegistry(path)
    source = _source()
    receipt = _ingest(registry, source)
    other = DatasetRegistry(path)
    epoch = registry.dataset_authority_epoch(receipt.dataset_digest)
    started = threading.Event()
    done = threading.Event()
    errors = []

    def revoke():
        started.set()
        try:
            other.revoke_source_rights(
                source.envelope.content_digest, reason="concurrent withdrawal", command_id="revoke"
            )
        except (sqlite3.Error, ValueError, RuntimeError, PermissionError) as exc:
            errors.append(exc)
        finally:
            done.set()

    with registry.training_authority(receipt.dataset_digest, epoch):
        worker = threading.Thread(target=revoke)
        worker.start()
        assert started.wait(1)
        assert not done.wait(0.05)
        registry.assert_dataset_authority(receipt.dataset_digest, epoch)
    worker.join(timeout=2)
    assert done.is_set() and not errors
    with pytest.raises(PermissionError):
        registry.assert_dataset_authority(receipt.dataset_digest, epoch)


def test_actual_multimodal_export_provenance_survives_native_materialization(tmp_path):
    corpus = MultimodalCorpus()
    record = corpus.ingest(
        record_id="document",
        modality=LearningModality.DOCUMENT,
        media_type="text/plain",
        payload=b"actual document source bytes",
        source_refs=("source:actual-document",),
        rights_refs=("rights:actual-consent",),
        extracted_text="actual governed projection",
        extractor_ref="extractor:fixture-v1",
    )
    exported, documents = corpus.export_text_training(
        (record.record_id,),
        export_id="actual-export",
        purpose="training",
        rights_policy={"rights:actual-consent": ("training",)},
    )
    path = tmp_path / "data.sqlite3"
    registry = DatasetRegistry(path)
    receipt = registry.ingest_export(exported, documents, dataset_id="multimodal-data", acquired_at=NOW)
    registry.close()
    registry = DatasetRegistry(path)
    source = registry.materialized_sources(receipt.dataset_digest)[0]
    assert source.evidence["multimodal_manifest"] == exported.as_dict()
    assert source.evidence["multimodal_manifest_digest"] == exported.digest
    assert source.rights_refs == record.rights_refs
    assert record.asset_digest in source.lineage_refs
    assert registry.training_corpus(receipt.dataset_digest) == documents
    with pytest.raises(ValueError, match="provenance mismatch"):
        replace(source, rights_refs=("rights:caller-replaced-license",))
    with pytest.raises(ValueError, match="provenance mismatch"):
        replace(source, evidence={"multimodal_manifest": {}, "multimodal_manifest_digest": exported.digest})
    assert registry.ingest_export(exported, documents, dataset_id="multimodal-data").digest == receipt.digest
    before = _counts(registry)
    with pytest.raises(ValueError):
        registry.ingest_export(exported, ("caller altered projection",), dataset_id="another")
    assert _counts(registry) == before


def test_simulated_export_cannot_grant_ordinary_native_training():
    corpus = MultimodalCorpus()
    corpus.ingest(
        record_id="simulated",
        modality=LearningModality.IMAGE,
        media_type="image/png",
        payload=b"simulated asset",
        source_refs=("simulation:scene",),
        rights_refs=("rights:simulation",),
        extracted_text="simulated projection",
        extractor_ref="simulation-extractor",
        simulated=True,
    )
    exported, documents = corpus.export_text_training(
        ("simulated",),
        export_id="simulation-export",
        purpose="simulation_training",
        rights_policy={"rights:simulation": ("simulation_training",)},
        allow_simulated=True,
    )
    registry = DatasetRegistry()
    receipt = registry.ingest_export(exported, documents, dataset_id="simulated-data", acquired_at=NOW)
    assert receipt.manifest.permitted_uses == ("simulation_training",)
    with pytest.raises(PermissionError, match="not permitted for training"):
        registry.training_corpus(receipt.dataset_digest)


def test_governed_data_contract_retains_planning_and_promotion_boundaries():
    from pathlib import Path

    contract = json.loads((Path(__file__).parents[2] / "machine/ai_governed_training_data.json").read_text())
    assert contract["canonical_owner"] == "skeleton/ai/runtime/training/data.py"
    assert contract["promotion_state"] == {
        "completion_checkbox": False,
        "implementation_signed": False,
        "verification_signed": False,
        "may_self_close": False,
    }


def test_latest_materialized_version_is_read_only_and_enforces_atomic_cas():
    registry = DatasetRegistry()
    assert registry.latest_materialized_version("governed-data") == 0
    assert _counts(registry) == (0,) * 8
    first = _ingest(registry)
    assert registry.latest_materialized_version("governed-data") == 1
    selected = registry.latest_materialized_version("governed-data")
    _ingest(
        registry,
        _source(("new source bytes",), source_id="fixture://next"),
        expected_version=selected,
        ingestion_id="second",
    )
    before = _counts(registry)
    with pytest.raises(ValueError, match="version conflict"):
        _ingest(
            registry,
            _source(("losing concurrent source",), source_id="fixture://losing"),
            expected_version=selected,
            ingestion_id="losing",
        )
    assert _counts(registry) == before
    assert registry.latest_materialized_version("governed-data") == 2
    registry.delete_dataset(first.dataset_digest, reason="deleted namespace", command_id="delete")
    with pytest.raises(PermissionError, match="deleted dataset namespace"):
        registry.latest_materialized_version("governed-data")


def test_reusing_actual_bytes_reloads_first_acquisition_metadata_for_new_version(tmp_path):
    path = tmp_path / "data.sqlite3"
    registry = DatasetRegistry(path)
    source = _source()
    assert registry.source_envelope(source.envelope.content_digest) is None
    _ingest(registry, source)
    registry.close()
    registry = DatasetRegistry(path)
    original = registry.source_envelope(source.envelope.content_digest)
    assert original == source.envelope
    assert original.acquired_at == NOW.isoformat()
    reused = replace(source, envelope=original)
    second = _ingest(
        registry,
        reused,
        ingestion_id="second-run",
        expected_version=registry.latest_materialized_version("governed-data"),
    )
    assert second.manifest.version == "2"
    assert registry._db.execute("SELECT COUNT(*) FROM materialized_source").fetchone()[0] == 1
    assert registry.training_corpus(second.dataset_digest) == source.documents()
    registry.revoke_source_rights(source.envelope.content_digest, reason="withdrawn", command_id="revoke")
    with pytest.raises(PermissionError, match="rights revoked"):
        registry.source_envelope(source.envelope.content_digest)


def test_document_sequence_rejects_generator_before_it_can_be_consumed():
    def unbounded():
        raise AssertionError("a generator must not be consumed")
        yield "never"

    with pytest.raises(TypeError, match="ordered text sequence"):
        document_sequence_digest(unbounded())


def test_raw_source_whitespace_and_evidence_have_preparse_bounds(monkeypatch):
    from skeleton.ai.runtime.training import data

    monkeypatch.setattr(data, "_MAX_SOURCE_BYTES", 128)
    payload = b" " * 128 + b'["small"]'
    envelope = IngestEnvelope.from_bytes(
        source_id="fixture:large",
        payload=payload,
        parser_version="json-documents@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    with pytest.raises(ValueError, match="raw byte bound"):
        MaterializedTrainingSource(envelope, payload, "json_documents", ("rights:fixture",))
    monkeypatch.setattr(data, "_MAX_EVIDENCE_BYTES", 64)
    source = _source()
    with pytest.raises(ValueError, match="encoded byte bound"):
        replace(source, evidence={"large": "x" * 128})


def test_sqlite_blob_lengths_are_checked_before_loading_corrupt_payload(monkeypatch):
    from skeleton.ai.runtime.training import data

    registry = DatasetRegistry()
    receipt = _ingest(registry)
    monkeypatch.setattr(data, "_MAX_SOURCE_BYTES", 128)
    registry._db.execute("UPDATE materialized_source SET payload=zeroblob(129)")
    registry._db.commit()
    with pytest.raises(ValueError, match="exceeds byte bounds"):
        registry.training_corpus(receipt.dataset_digest)


def test_stored_metadata_bound_counts_utf8_bytes_before_loading(monkeypatch):
    from skeleton.ai.runtime.training import data

    registry = DatasetRegistry()
    receipt = _ingest(registry)
    monkeypatch.setattr(data, "_MAX_IDENTITY_BYTES", 256)
    registry._db.execute("UPDATE materialized_source SET source_json=?", ("😀" * 100,))
    registry._db.commit()
    with pytest.raises(ValueError, match="exceeds byte bounds"):
        registry._source_blob(receipt.manifest.source_ingest_digests[0])


def test_materialized_split_sources_cannot_consume_an_unbounded_generator():
    registry = DatasetRegistry()

    def unbounded():
        raise AssertionError("sources must not be consumed")
        yield _source()

    with pytest.raises(TypeError, match="ordered source sequence"):
        _ingest(registry, sources={"train": unbounded()})
    assert _counts(registry) == (0,) * 8


@pytest.mark.parametrize("when", ("before", "inside"))
def test_publication_guard_revalidates_corrupt_materialized_bytes_even_without_epoch_change(when):
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    epoch = registry.dataset_authority_epoch(receipt.dataset_digest)
    entered = False
    if when == "before":
        registry._db.execute("UPDATE materialized_source SET payload=?", (b"corrupt source",))
        registry._db.commit()
    with (
        pytest.raises(ValueError, match="content digest"),
        registry.training_authority(receipt.dataset_digest, epoch),
    ):
        entered = True
        registry._db.execute("UPDATE materialized_source SET payload=?", (b"corrupt source",))
    assert entered is (when == "inside")
    assert registry.dataset_authority_epoch(receipt.dataset_digest) == epoch
    if when == "inside":
        assert registry.training_corpus(receipt.dataset_digest) == _source().documents()


def test_publication_guard_blocks_a_late_failed_quality_report_even_without_epoch_change():
    registry = DatasetRegistry()
    receipt = _ingest(registry)
    epoch = registry.dataset_authority_epoch(receipt.dataset_digest)
    existing = registry.latest_quality(receipt.dataset_digest)
    failed = DataQualityReport.evaluate(
        receipt.dataset_digest,
        (*existing.rules, DataQualityRule("late-failure", "record_count", ">=", 999)),
        existing.metrics,
        observation_digest=existing.observation_digest,
        split_sequence_digests=existing.split_sequence_digests,
    )
    registry._db.execute(
        "INSERT INTO quality_report VALUES (?, ?, ?, 0)",
        (
            failed.digest,
            receipt.dataset_digest,
            json.dumps(failed.as_dict(), sort_keys=True, separators=(",", ":")),
        ),
    )
    registry._db.commit()
    assert registry.dataset_authority_epoch(receipt.dataset_digest) == epoch
    with (
        pytest.raises(RuntimeError, match="critical quality"),
        registry.training_authority(receipt.dataset_digest, epoch),
    ):
        pytest.fail("publication must never be admitted")


def test_speech_recovery_snapshot_is_durable_but_cannot_enter_training(tmp_path):
    path = tmp_path / "speech.sqlite3"
    registry = DatasetRegistry(path)
    source = _source(("explicitly consented bounded speech snapshot",), rights=("speech_recovery",))
    receipt = _ingest(
        registry, source, sources={"speech_snapshot": (source,)}, permitted_uses=("speech_recovery",)
    )
    assert registry.materialized_sources(receipt.dataset_digest) == (source,)
    registry.close()
    registry = DatasetRegistry(path)
    assert registry.materialized_ingestion(receipt.ingestion_id) == receipt
    assert registry.materialized_sources(receipt.dataset_digest) == (source,)
    epoch = registry.dataset_authority_epoch(receipt.dataset_digest)
    for operation in (
        lambda: registry.training_corpus(receipt.dataset_digest, split_name="speech_snapshot"),
        lambda: registry.validate_training_corpus(
            receipt.dataset_digest, source.documents(), split_name="speech_snapshot"
        ),
        lambda: registry.assert_dataset_authority(receipt.dataset_digest, epoch),
    ):
        with pytest.raises(PermissionError, match="training"):
            operation()
    runs = TrainingRepository()
    with pytest.raises(PermissionError, match="training"):
        runs.register_run(_run_manifest(receipt.manifest), registry)
    registry.revoke_source_rights(
        source.envelope.content_digest,
        uses=("speech_recovery",),
        reason="consent withdrawn",
        command_id="withdraw",
    )
    with pytest.raises(PermissionError, match="revoked"):
        registry.materialized_sources(receipt.dataset_digest)


@pytest.mark.parametrize("uses", (("speech_recovery", "training"), ("evaluation", "speech_recovery")))
def test_speech_recovery_cannot_mix_with_model_data_purposes_or_publish_partial_state(uses):
    registry = DatasetRegistry()
    before = _counts(registry)
    with pytest.raises(ValueError, match="isolated"):
        _ingest(registry, _source(rights=uses), permitted_uses=uses)
    assert _counts(registry) == before


def test_speech_recovery_rights_cannot_be_widened_into_training_or_projection_export():
    registry = DatasetRegistry()
    before = _counts(registry)
    with pytest.raises(PermissionError, match="rights"):
        _ingest(registry, _source(rights=("speech_recovery",)))
    assert _counts(registry) == before
    corpus = MultimodalCorpus()
    with pytest.raises(RuntimeError, match="purpose"):
        corpus.export_text_training(
            ("snapshot",), export_id="recovery-as-training", purpose="speech_recovery", rights_policy={}
        )
