from __future__ import annotations

import dataclasses

import pytest

from skeleton.ai.runtime.learning_foundation.data import (
    ContentAddressedStore,
    DataConflictError,
    DataPlaneError,
    DatasetRecord,
    DatasetRegistry,
)


def test_content_address_identity_is_stable_and_verified() -> None:
    store = ContentAddressedStore()
    first = store.put(b"alpha", media_type="text/plain")
    second = store.put(b"alpha", media_type="text/plain")
    assert first == second
    assert first.uri.startswith("sha256:")
    assert store.get(first.digest) == b"alpha"
    with pytest.raises(DataPlaneError, match="media type"):
        store.put(b"alpha", media_type="application/json")


def test_dataset_ingestion_binds_rights_lineage_quality_and_synthetic_provenance() -> None:
    registry = DatasetRegistry()
    record, receipt = registry.ingest(
        ingestion_id="ingest-1",
        dataset_id="train-a",
        samples=[b"one", b"two", b"two"],
        source_refs=("source:fixture",),
        rights_refs=("rights:fixture",),
        lineage_refs=("lineage:raw:v1",),
        expected_version=0,
        synthetic=True,
        generator_ref="generator:fixture:v1",
        metadata={"split": "train"},
    )
    assert record.version == 1
    assert record.synthetic is True
    assert record.generator_ref == "generator:fixture:v1"
    assert record.quality is not None
    assert record.quality.duplicate_sample_count == 1
    assert record.quality.quality_score < 1.0
    assert receipt.manifest_digest == record.manifest_digest

    training = record.as_training_dataset()
    assert training.dataset_id.startswith("train-a@1:")
    assert training.rights_refs == ("rights:fixture",)
    assert training.metadata["synthetic"] is True


def test_ingestion_is_idempotent_by_ingestion_identity() -> None:
    registry = DatasetRegistry()
    first, receipt = registry.ingest(
        ingestion_id="stable-op",
        dataset_id="data",
        samples=[b"x"],
        source_refs=("source:x",),
        rights_refs=("rights:x",),
    )
    second, replay = registry.ingest(
        ingestion_id="stable-op",
        dataset_id="data",
        samples=[b"different"],
        source_refs=("source:other",),
        rights_refs=("rights:other",),
    )
    assert second == first
    assert replay == receipt
    assert len(registry.history("data")) == 1


def test_stale_ingestion_fails_closed() -> None:
    registry = DatasetRegistry()
    registry.ingest(
        ingestion_id="v1",
        dataset_id="data",
        samples=[b"x"],
        source_refs=("source:x",),
        rights_refs=("rights:x",),
    )
    with pytest.raises(DataConflictError, match="expected=0 actual=1"):
        registry.ingest(
            ingestion_id="stale",
            dataset_id="data",
            samples=[b"y"],
            source_refs=("source:y",),
            rights_refs=("rights:y",),
            expected_version=0,
        )


def test_multi_dataset_transaction_checks_every_version_before_commit() -> None:
    registry = DatasetRegistry()
    a, _ = registry.ingest(
        ingestion_id="a1", dataset_id="a", samples=[b"a"],
        source_refs=("source:a",), rights_refs=("rights:a",),
    )
    b, _ = registry.ingest(
        ingestion_id="b1", dataset_id="b", samples=[b"b"],
        source_refs=("source:b",), rights_refs=("rights:b",),
    )
    a2 = dataclasses.replace(a, version=2)
    b2 = dataclasses.replace(b, version=2)

    with pytest.raises(DataConflictError):
        registry.transact(
            transaction_id="tx-stale",
            expected_versions={"a": 1, "b": 0},
            replacements={"a": a2, "b": b2},
        )
    assert registry.current("a").version == 1
    assert registry.current("b").version == 1

    receipt = registry.transact(
        transaction_id="tx-ok",
        expected_versions={"a": 1, "b": 1},
        replacements={"a": a2, "b": b2},
    )
    assert receipt.before_versions == {"a": 1, "b": 1}
    assert receipt.after_versions == {"a": 2, "b": 2}
    assert registry.current("a").version == 2
    assert registry.current("b").version == 2


def test_non_synthetic_record_cannot_claim_generator() -> None:
    registry = DatasetRegistry()
    with pytest.raises(DataPlaneError, match="non-synthetic"):
        registry.ingest(
            ingestion_id="bad-generator",
            dataset_id="data",
            samples=[b"x"],
            source_refs=("source:x",),
            rights_refs=("rights:x",),
            synthetic=False,
            generator_ref="generator:should-not-exist",
        )
