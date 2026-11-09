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

def test_quality_report_cannot_forge_passing_outcome():
    rule=DataQualityRule(
        "validity",
        "valid_fraction",
        ">=",
        0.99,
        critical=True,
    )
    with pytest.raises(ValueError,match="outcome does not match"):
        DataQualityReport(
            dataset_digest=_digest("dataset"),
            rules=(rule,),
            metrics={"valid_fraction":0.1},
            passed_rule_ids=("validity",),
            failed_rule_ids=(),
        )


def test_empty_quality_policy_cannot_make_dataset_training_ready(tmp_path):
    registry,manifest=_ready_registry(tmp_path)
    with pytest.raises(ValueError,match="requires at least one rule"):
        DataQualityReport(
            dataset_digest=manifest.digest,
            rules=(),
            metrics={},
            passed_rule_ids=(),
            failed_rule_ids=(),
        )


def test_quality_report_rejects_nonfinite_metric():
    rule=DataQualityRule("finite","score",">=",0.0)
    with pytest.raises(ValueError,match="metrics must be finite"):
        DataQualityReport.evaluate(
            _digest("dataset"),
            (rule,),
            {"score":float("nan")},
        )


def test_latest_quality_detects_persisted_pass_flag_tampering(tmp_path):
    registry,manifest=_ready_registry(tmp_path)
    report=DataQualityReport.evaluate(
        manifest.digest,
        (DataQualityRule("validity","valid_fraction",">=",0.99),),
        {"valid_fraction":1.0},
    )
    registry.record_quality(report)
    registry._db.execute(
        "UPDATE quality_report SET passed=0 WHERE report_digest=?",
        (report.digest,),
    )
    registry._db.commit()

    with pytest.raises(ValueError,match="pass flag mismatch"):
        registry.latest_quality(manifest.digest)


def test_dataset_read_detects_registry_key_payload_tampering(tmp_path):
    registry,manifest=_ready_registry(tmp_path)
    payload=manifest.as_dict()
    payload["dataset_id"]="tampered-id"
    payload.pop("dataset_digest",None)
    from skeleton.ai.runtime.training.data import _sha256
    payload["dataset_digest"]=_sha256({k:v for k,v in payload.items() if k!="dataset_digest"})
    registry._db.execute(
        "UPDATE dataset_manifest SET manifest_json=? WHERE dataset_digest=?",
        (json.dumps(payload,sort_keys=True,separators=(",",":")),manifest.digest),
    )
    registry._db.commit()

    with pytest.raises(ValueError,match="does not match registry key"):
        registry.dataset(manifest.digest)



def test_dataset_cannot_escalate_source_rights_to_training(tmp_path):
    registry=DatasetRegistry(tmp_path/"rights.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://evaluation-only",
        payload=b"evaluation only",
        parser_version="parser@1",
        classification="internal",
        rights=("evaluation",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="rights-escalation",
        version="1",
        splits=(DatasetSplit("train",_digest("rights-split"),1),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("parser@1",),
    )

    with pytest.raises(PermissionError,match="escalate source ingest rights"):
        registry.register_dataset(manifest)


def test_dataset_cannot_downgrade_source_classification(tmp_path):
    registry=DatasetRegistry(tmp_path/"classification.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://restricted",
        payload=b"restricted source",
        parser_version="parser@1",
        classification="restricted",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="classification-downgrade",
        version="1",
        splits=(DatasetSplit("train",_digest("classification-split"),1),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="restricted-development",
        parser_versions=("parser@1",),
    )

    with pytest.raises(PermissionError,match="may not downgrade"):
        registry.register_dataset(manifest)


def test_dataset_must_preserve_source_parser_identity(tmp_path):
    registry=DatasetRegistry(tmp_path/"parser.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://parser",
        payload=b"parser-bound",
        parser_version="source-parser@7",
        classification="internal",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="parser-drift",
        version="1",
        splits=(DatasetSplit("train",_digest("parser-split"),1),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("different-parser@1",),
    )

    with pytest.raises(ValueError,match="omit source parser"):
        registry.register_dataset(manifest)


def test_dataset_may_be_more_restrictive_than_its_source(tmp_path):
    registry=DatasetRegistry(tmp_path/"restrictive.sqlite3")
    ingest=IngestEnvelope.from_bytes(
        source_id="fixture://public",
        payload=b"public source",
        parser_version="parser@1",
        classification="public",
        rights=("training","evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(ingest)
    manifest=DatasetManifest(
        dataset_id="more-restrictive",
        version="1",
        splits=(DatasetSplit("train",_digest("restrictive-split"),1),),
        source_ingest_digests=(ingest.content_digest,),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("parser@1",),
    )

    assert registry.register_dataset(manifest)==manifest.digest


def test_multi_source_dataset_uses_intersection_of_source_rights(tmp_path):
    registry=DatasetRegistry(tmp_path/"multi-rights.sqlite3")
    training=IngestEnvelope.from_bytes(
        source_id="fixture://training-source",
        payload=b"training source",
        parser_version="parser@1",
        classification="internal",
        rights=("training","evaluation"),
        trusted=True,
        acquired_at=NOW,
    )
    evaluation=IngestEnvelope.from_bytes(
        source_id="fixture://evaluation-source",
        payload=b"evaluation source",
        parser_version="parser@2",
        classification="internal",
        rights=("evaluation",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(training)
    registry.register_ingest(evaluation)
    manifest=DatasetManifest(
        dataset_id="multi-source-rights",
        version="1",
        splits=(DatasetSplit("train",_digest("multi-rights"),2),),
        source_ingest_digests=(training.content_digest,evaluation.content_digest),
        classification="internal",
        permitted_uses=("training",),
        retention_class="model-development",
        parser_versions=("parser@1","parser@2"),
    )

    with pytest.raises(PermissionError,match="escalate source ingest rights"):
        registry.register_dataset(manifest)


def test_multi_source_dataset_preserves_strictest_classification_and_all_parsers(tmp_path):
    registry=DatasetRegistry(tmp_path/"multi-authority.sqlite3")
    public=IngestEnvelope.from_bytes(
        source_id="fixture://public-source",
        payload=b"public multi source",
        parser_version="public-parser@1",
        classification="public",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    restricted=IngestEnvelope.from_bytes(
        source_id="fixture://restricted-source",
        payload=b"restricted multi source",
        parser_version="restricted-parser@3",
        classification="restricted",
        rights=("training",),
        trusted=True,
        acquired_at=NOW,
    )
    registry.register_ingest(public)
    registry.register_ingest(restricted)

    downgraded=DatasetManifest(
        dataset_id="multi-source-classification",
        version="1",
        splits=(DatasetSplit("train",_digest("multi-class"),2),),
        source_ingest_digests=(public.content_digest,restricted.content_digest),
        classification="confidential",
        permitted_uses=("training",),
        retention_class="restricted-development",
        parser_versions=("public-parser@1","restricted-parser@3"),
    )
    with pytest.raises(PermissionError,match="may not downgrade"):
        registry.register_dataset(downgraded)

    missing_parser=DatasetManifest(
        dataset_id="multi-source-parser",
        version="1",
        splits=(DatasetSplit("train",_digest("multi-parser"),2),),
        source_ingest_digests=(public.content_digest,restricted.content_digest),
        classification="restricted",
        permitted_uses=("training",),
        retention_class="restricted-development",
        parser_versions=("public-parser@1",),
    )
    with pytest.raises(ValueError,match="omit source parser"):
        registry.register_dataset(missing_parser)
