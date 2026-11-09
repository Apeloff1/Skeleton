"""Novel original world candidate batches stay truthful about unreleased games."""
from __future__ import annotations
from pathlib import Path
import json,pytest

from skeleton.ai.webcrawler.dragon_route_world_batch import (
    SCHEMA,MAX_BATCH,LEGAL_HOLDS,
    create_candidate_batch,verify_batch,batch_dict,publish_candidate_batch,
)


def test_original_world_candidate_batches_are_exactly_resumable_not_fake_games():
    first=create_candidate_batch(start_seed=1977,count=3,weather="rain",
                                 hour=8,audit_budget=1200)
    assert first.schema==SCHEMA
    assert first.attempted==3
    assert first.admitted==3 and first.rejected==0
    assert first.produced_finished_games==0
    assert first.next_seed==1980
    assert len(first.candidates)==3
    assert len({x.digest for x in first.candidates})==3
    assert all(x.shipped_full_game is False and
               x.external_content_imported is False and
               x.status=="accepted_original_world_candidate_pending_all_release_reviews"
               for x in first.candidates)
    assert len(LEGAL_HOLDS)>=7
    encoded=json.loads(json.dumps(batch_dict(first)))
    assert verify_batch(encoded)==first
    second=create_candidate_batch(start_seed=first.next_seed,count=2,
        weather="rain",hour=8,
        examined_digests=frozenset(x.digest for x in first.candidates),
        audit_budget=1200)
    assert second.next_seed==1982
    assert second.admitted==2
    assert set(x.digest for x in second.candidates).isdisjoint(
        x.digest for x in first.candidates)
    assert verify_batch(json.loads(json.dumps(batch_dict(second))))==second


def test_recomputed_world_candidate_manifests_reject_false_shipment_status():
    value=json.loads(json.dumps(batch_dict(
        create_candidate_batch(start_seed=5,count=1,audit_budget=1200),
    )))
    value["produced_finished_games"]=1000000
    with pytest.raises(ValueError):
        verify_batch(value)
    value["produced_finished_games"]=0
    value["candidates"][0]["external_content_imported"]=True
    with pytest.raises(ValueError):
        verify_batch(value)


def test_content_addressed_candidate_manifest_is_exported_without_fake_native_build(tmp_path):
    batch=create_candidate_batch(start_seed=1977,count=2,audit_budget=1200)
    with pytest.raises(PermissionError):
        publish_candidate_batch(batch,tmp_path,authorized=False)
    result=publish_candidate_batch(batch,tmp_path,authorized=True)
    assert result["status"]=="original_candidate_manifest_not_finished_games"
    assert result["finished_games"]==0
    doc=json.loads((tmp_path/result["filename"]).read_text())
    assert verify_batch(doc)==batch
    assert all("review" in x for x in doc["legal_holds"]
               if x.startswith("original_expression"))


@pytest.mark.parametrize("options",[
    {"start_seed":-1,"count":1},
    {"start_seed":True,"count":1},
    {"start_seed":2**32,"count":1},
    {"start_seed":2**32-1,"count":2},
    {"start_seed":2,"count":0},
    {"start_seed":2,"count":MAX_BATCH+1},
    {"start_seed":2,"count":True},
    {"start_seed":2,"count":1,"audit_budget":20},
    {"start_seed":2,"count":1,"examined_digests":frozenset({"malformed"})},
])
def test_huge_candidate_pipeline_fails_closed_on_excessive_or_forged_work(options):
    with pytest.raises(ValueError):
        create_candidate_batch(**options)
