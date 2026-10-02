from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from skeleton.data.native_pipeline import (
    DataQualityError,
    DatasetConflict,
    DatasetCorruption,
    NativeDatasetRepository,
    QualityPolicy,
)


NOW=datetime(2026,10,2,6,0,tzinfo=timezone.utc)
SCHEMA={
    "type":"array",
    "items":{
        "type":"object",
        "properties":{"id":{"type":"integer"},"text":{"type":"string"}},
        "required":["id","text"],
    },
}


def _repo(tmp_path):
    return NativeDatasetRepository(
        tmp_path/"datasets.sqlite3",
        cas_root=tmp_path/"cas",
    )


def test_commit_roundtrip_has_stable_content_identity(tmp_path) -> None:
    rows=[{"id":1,"text":"alpha"},{"id":2,"text":"beta"}]
    policy=QualityPolicy(required_fields=("id","text"),unique_fields=("id",))
    with _repo(tmp_path) as repo:
        first=repo.commit(
            tenant_id="tenant-a",
            dataset_id="train",
            rows=rows,
            schema=SCHEMA,
            source_id="fixture",
            quality_policy=policy,
            expected_version=0,
            now=NOW,
        )
        stored,decoded=repo.get(tenant_id="tenant-a",dataset_id="train")
    assert first.version==1
    assert stored==first
    assert decoded==rows
    assert len(first.payload_digest)==64
    assert len(first.manifest_digest)==64


def test_version_compare_and_advance_is_fail_closed(tmp_path) -> None:
    policy=QualityPolicy(required_fields=("id",),unique_fields=("id",))
    with _repo(tmp_path) as repo:
        repo.commit(
            tenant_id="tenant-a",dataset_id="train",rows=[{"id":1}],
            schema=SCHEMA,source_id="fixture",quality_policy=policy,
            expected_version=0,now=NOW,
        )
        with pytest.raises(DatasetConflict,match="stale dataset version"):
            repo.commit(
                tenant_id="tenant-a",dataset_id="train",rows=[{"id":2}],
                schema=SCHEMA,source_id="fixture",quality_policy=policy,
                expected_version=0,now=NOW,
            )


def test_quality_rejects_missing_and_duplicate_identity(tmp_path) -> None:
    with _repo(tmp_path) as repo:
        with pytest.raises(DataQualityError,match="quality policy failed"):
            repo.commit(
                tenant_id="tenant-a",
                dataset_id="bad",
                rows=[{"id":1,"text":""},{"id":1,"text":"ok"}],
                schema=SCHEMA,
                source_id="fixture",
                quality_policy=QualityPolicy(
                    required_fields=("id","text"),
                    unique_fields=("id",),
                ),
                expected_version=0,
                now=NOW,
            )


def test_deterministic_derivation_retains_parent_lineage(tmp_path) -> None:
    policy=QualityPolicy(required_fields=("id","text"))
    with _repo(tmp_path) as repo:
        parent=repo.commit(
            tenant_id="tenant-a",
            dataset_id="source",
            rows=[{"id":1,"text":"alpha"},{"id":2,"text":"beta"}],
            schema=SCHEMA,
            source_id="fixture",
            quality_policy=policy,
            expected_version=0,
            now=NOW,
        )
        derived=repo.derive_sample(
            tenant_id="tenant-a",
            parent_dataset_id="source",
            output_dataset_id="synthetic",
            count=4,
            seed=17,
            quality_policy=policy,
            now=NOW,
        )
        _,rows=repo.get(tenant_id="tenant-a",dataset_id="synthetic")
        lineage=repo.lineage(
            tenant_id="tenant-a",
            manifest_digest=derived.manifest_digest,
        )
    assert len(rows)==4
    assert derived.parent_manifest_digests==(parent.manifest_digest,)
    assert lineage==(parent.manifest_digest,)


def test_tenant_scope_does_not_leak_dataset_identity(tmp_path) -> None:
    policy=QualityPolicy(required_fields=("id",))
    with _repo(tmp_path) as repo:
        repo.commit(
            tenant_id="tenant-a",dataset_id="private",rows=[{"id":1}],
            schema=SCHEMA,source_id="fixture",quality_policy=policy,
            expected_version=0,now=NOW,
        )
        with pytest.raises(Exception,match="not found"):
            repo.get(tenant_id="tenant-b",dataset_id="private")


def test_read_detects_cas_tampering(tmp_path) -> None:
    policy=QualityPolicy(required_fields=("id",))
    with _repo(tmp_path) as repo:
        record=repo.commit(
            tenant_id="tenant-a",dataset_id="train",rows=[{"id":1}],
            schema=SCHEMA,source_id="fixture",quality_policy=policy,
            expected_version=0,now=NOW,
        )
        path=repo.cas._path(record.payload_digest)
        path.write_text(json.dumps([{"id":999}]),encoding="utf-8")
        with pytest.raises(DatasetCorruption,match="digest mismatch"):
            repo.get(tenant_id="tenant-a",dataset_id="train")
