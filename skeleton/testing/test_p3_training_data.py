from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import pytest

from skeleton.ai.runtime.training.data import (
    DataQualityReport,
    DataQualityRule,
    DatasetManifest,
    DatasetRegistry,
    DatasetSplit,
    IngestEnvelope,
    LineageReceipt,
    SyntheticDataReceipt,
)


NOW=datetime(2026,10,2,8,0,tzinfo=timezone.utc)


def _digest(text:str)->str:
    return hashlib.sha256(text.encode()).hexdigest()


def _ready_registry(tmp_path):
    registry=DatasetRegistry(tmp_path/"datasets.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://training-corpus",
        payload=b"alpha beta gamma",
        parser_version="fixture-parser@1",
        classification="internal",
        rights=("training","evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="train-core",
        version="1.0.0",
        splits=(
            DatasetSplit("train",_digest("train-split"),100),
            DatasetSplit("validation",_digest("validation-split"),20),
        ),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training","evaluation"),
        retention_class="model-development",
        parser_versions=("fixture-parser@1",),
    )
    registry.register_dataset(manifest)
    return registry, manifest


def test_dataset_identity_is_immutable_and_content_addressed(tmp_path):
    registry, manifest=_ready_registry(tmp_path)
    assert registry.dataset(manifest.digest).as_dict()==manifest.as_dict()

    conflicting=DatasetManifest(
        dataset_id=manifest.dataset_id,
        version=manifest.version,
        splits=(DatasetSplit("train",_digest("changed"),999),),
        source_ingest_digests=manifest.source_ingest_digests,
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("fixture-parser@1",),
    )
    with pytest.raises(ValueError,match="immutable"):
        registry.register_dataset(conflicting)


def test_quarantined_ingest_cannot_enter_dataset_registry(tmp_path):
    registry=DatasetRegistry(tmp_path/"datasets.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://bad",
        payload=b"untrusted",
        parser_version="parser@1",
        classification="internal",
        rights=("training",),
        trusted=False,
        quarantine_reason="malformed input",
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="bad",
        version="1",
        splits=(DatasetSplit("train",_digest("bad-split"),1),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="quarantine",
        parser_versions=("parser@1",),
    )
    with pytest.raises(ValueError,match="quarantined"):
        registry.register_dataset(manifest)


def test_quality_gate_blocks_training_until_critical_rules_pass(tmp_path):
    registry, manifest=_ready_registry(tmp_path)
    rules=(
        DataQualityRule("validity","valid_fraction",">=",0.99,critical=True),
        DataQualityRule("duplication","duplicate_fraction","<=",0.02,critical=True),
        DataQualityRule("style","style_score",">=",0.5,critical=False),
    )
    failed=DataQualityReport.evaluate(
        manifest.digest,rules,
        {"valid_fraction":0.995,"duplicate_fraction":0.4,"style_score":0.2},
    )
    registry.record_quality(failed)
    with pytest.raises(RuntimeError,match="critical quality"):
        registry.require_training_ready(manifest.digest)

    passed=DataQualityReport.evaluate(
        manifest.digest,rules,
        {"valid_fraction":0.999,"duplicate_fraction":0.01,"style_score":0.2},
    )
    registry.record_quality(passed)
    assert registry.require_training_ready(manifest.digest).digest==manifest.digest


def test_lineage_binds_inputs_transform_code_environment_and_output(tmp_path):
    registry, manifest=_ready_registry(tmp_path)
    receipt=LineageReceipt(
        transform_id="normalize@1",
        input_digests=(manifest.digest,),
        output_digest=_digest("normalized-output"),
        environment_digest=_digest("python-3.11"),
        code_digest=_digest("normalize-code"),
        created_at=NOW.isoformat(),
    )
    assert len(registry.record_lineage(receipt))==64


def test_synthetic_origin_is_permanent_manifest_identity(tmp_path):
    registry, base=_ready_registry(tmp_path)
    quality=DataQualityReport.evaluate(
        base.digest,
        (DataQualityRule("validity","valid_fraction",">=",0.9),),
        {"valid_fraction":1.0},
    )
    registry.record_quality(quality)
    synthetic=SyntheticDataReceipt(
        generator_id="local-generator@1",
        generator_config_digest=_digest("config"),
        source_dataset_digests=(base.digest,),
        seed=7,
        generated_record_count=50,
    )
    ingest=IngestEnvelope.from_bytes(
        source_id="synthetic://local-generator@1",
        payload=b"generated corpus",
        parser_version="synthetic-parser@1",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="synthetic-core",
        version="1",
        splits=(DatasetSplit("train",_digest("synthetic-split"),50),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("synthetic-parser@1",),
        synthetic_receipt=synthetic,
    )
    registry.register_dataset(manifest)
    restored=registry.dataset(manifest.digest)
    assert restored.synthetic_receipt is not None
    assert restored.synthetic_receipt.digest==synthetic.digest


def test_manifest_digest_detects_serialized_tampering(tmp_path):
    registry, manifest=_ready_registry(tmp_path)
    payload=manifest.as_dict()
    payload["classification"]="public"
    with pytest.raises(ValueError,match="digest mismatch"):
        DatasetManifest.from_dict(payload)
