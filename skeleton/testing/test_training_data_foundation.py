from __future__ import annotations

import hashlib

from skeleton.ai.runtime.training import (
    ContentAddressedCache,
    DataIngestionEngine,
    DatasetManifest,
    DatasetRecord,
    DocumentIntelligence,
    LicensePolicyRegistry,
    LineageGraph,
    SyntheticDataFactory,
)
from skeleton.ai.runtime.training.data import LicensePolicy


def test_cache_is_tenant_isolated_and_source_invalidatable() -> None:
    cache=ContentAddressedCache()
    source=hashlib.sha256(b"source").hexdigest()
    cache.put(namespace="dataset",tenant_id="a",key={"id":1},payload={"v":1},source_digest=source)
    cache.put(namespace="dataset",tenant_id="b",key={"id":1},payload={"v":2},source_digest=source)
    assert cache.get(namespace="dataset",tenant_id="a",key={"id":1})=={"v":1}
    assert cache.get(namespace="dataset",tenant_id="b",key={"id":1})=={"v":2}
    assert cache.invalidate_source(source)==2


def test_ingestion_quarantines_duplicates_and_oversize() -> None:
    ingest=DataIngestionEngine(max_bytes=12)
    record,receipt=ingest.ingest(
        record_id="r1",text="hello",source_ref="fixture",license_id="CC0",usage_grant="train"
    )
    assert record is not None and receipt.quarantined is False
    duplicate,dup_receipt=ingest.ingest(
        record_id="r2",text="hello",source_ref="fixture2",license_id="CC0",usage_grant="train"
    )
    assert duplicate is None and dup_receipt.reason=="duplicate_content"
    oversized,over_receipt=ingest.ingest(
        record_id="r3",text="this is much too long",source_ref="fixture3",license_id="CC0",usage_grant="train"
    )
    assert oversized is None and over_receipt.reason=="size_limit"


def test_document_regions_preserve_page_offsets_and_source_identity() -> None:
    text="page one\fpage two"
    regions=DocumentIntelligence.extract(text)
    assert [r.page_index for r in regions]==[0,1]
    assert regions[0].text=="page one"
    assert regions[1].text=="page two"
    assert regions[0].source_digest==regions[1].source_digest
    assert len({r.evidence_digest for r in regions})==2


def test_lineage_tracks_transitive_ancestry() -> None:
    graph=LineageGraph()
    a=hashlib.sha256(b"a").hexdigest()
    b=hashlib.sha256(b"b").hexdigest()
    c=hashlib.sha256(b"c").hexdigest()
    graph.add_node(a)
    graph.transform(parent_digest=a,child_digest=b,transformation="clean")
    graph.transform(parent_digest=b,child_digest=c,transformation="tokenize")
    assert graph.ancestors(c)==tuple(sorted((a,b)))


def test_license_policy_fails_closed_and_respects_derivative_rights() -> None:
    record=DatasetRecord("r","text","fixture","L1","train")
    policies=LicensePolicyRegistry((
        LicensePolicy("L1",True,False,("local-model-training",)),
    ))
    assert policies.evaluate(record).permitted is True
    denied=policies.evaluate(record,derivative=True)
    assert denied.permitted is False
    assert denied.reason_code=="license_denies_derivatives"
    unknown=policies.evaluate(DatasetRecord("u","text2","fixture","UNKNOWN","train"))
    assert unknown.permitted is False
    assert unknown.reason_code=="unknown_license"


def test_synthetic_factory_is_deterministic_and_parent_bound() -> None:
    base=DatasetManifest(
        dataset_id="base",version="1",
        records=(
            DatasetRecord("r1","alpha","fixture:r1","CC0","train_eval"),
            DatasetRecord("r2","beta","fixture:r2","CC0","train_eval"),
        ),
    )
    factory=SyntheticDataFactory()
    one=factory.derive(base,transform_id="upper",transform=str.upper)
    two=factory.derive(base,transform_id="upper",transform=str.upper)
    assert one.digest==two.digest
    assert [r.text for r in one.records]==["ALPHA","BETA"]
    assert one.records[0].synthetic_parent_refs==("r1",)
