"""Complete original lens catalogue and externally scoped receipt custody."""
import hashlib
import hmac
from copy import deepcopy

import pytest

from skeleton.app.recovered_evidence import canonical,digest,EvidenceError
from skeleton.app.emulator_lens_work_index import load_index,LANES
from skeleton.app.emulator_lens_receipt_queue import page_queue,GENESIS
from skeleton.testing.test_jeeves_emulator_full_lens_review import _synthetic_report

KEYS={lane:bytes([index+1])*32 for index,lane in enumerate(LANES)}


@pytest.fixture(scope="module")
def index():
    source=_synthetic_report(runs=32)
    return load_index(source,expected_source_digest=source["report_digest"],authorized=True)


def signed(index,task,sequence,prior,*,reviewer=None,artifact=None,outcome="observed",key=None):
    body={"schema":"skeleton.emulator-lens-work-receipt.v1",
          "index_digest":index.identity,"task_id":task["task_id"],"lane":task["lane"],
          "review_id":task["review_id"],"source_report_digest":index.source_digest,
          "catalog_digest":index.catalog_digest,"source_receipt_set_digest":task["source_receipt_set_digest"],
          "outcome":outcome,"artifact_sha256":artifact or digest([task["task_id"],"fixture"]),
          "consent_scope_sha256":"a"*64,"reviewer_id":reviewer or task["lane"],
          "sequence":sequence,"previous":prior}
    return {**body,"signature":hmac.new(key or KEYS[task["lane"]],canonical(body),hashlib.sha256).hexdigest()}


def ready(index):
    first=next(t for t in index.tasks if t["material_ready"])
    return [t for t in index.tasks if t["review_id"]==first["review_id"]]


def queue(index,rows=(),**kw):
    rows=list(rows)
    return page_queue(index,rows,keys=kw.pop("keys",KEYS),
                      expected_head=kw.pop("expected_head",digest(rows[-1]) if rows else GENESIS),
                      authorized=True,**kw)


def test_full_canonical_registry_has_three_distinct_work_lanes(index):
    report=queue(index,page_size=17)
    assert report["lens_count"]>=200
    assert report["task_count"]==report["lens_count"]*3
    assert sum(report["counts"].values())==report["task_count"]
    assert len(report["rows"])==17
    assert report["next_page"]==1
    assert report["signed_receipt_count"]==0
    assert not report["production_model_promotion_authorized"]


def test_counts_are_reconciled_without_native_evidence_inference(index):
    tasks=ready(index)
    rows=[]
    for i,task in enumerate(tasks):
        rows.append(signed(index,task,i,digest(rows[-1]) if rows else GENESIS,
                           outcome="counterexample" if task["lane"]=="adversarial_review" else "observed"))
    report=queue(index,rows)
    assert report["signed_receipt_count"]==3
    assert report["rows"][0]["submission_state"]=="signed_metadata_counterexample"
    assert report["counts"]["signed_metadata_observed"]==2
    assert not report["semantic_triangulation_completed"]
    assert report["independent_dragon_observations_verified"]==0
    assert not report["native_artifact_bytes_checked"]


def test_wrong_lane_and_independent_key_reuse_rejected(index):
    task=ready(index)[0]
    other=next(k for lane,k in KEYS.items() if lane!=task["lane"])
    row=signed(index,task,0,GENESIS,key=other)
    with pytest.raises(EvidenceError,match="seal"):
        queue(index,[row])
    with pytest.raises(EvidenceError,match="independent"):
        queue(index,keys={lane:b"a"*32 for lane in LANES})


def test_scope_reviewer_and_artifact_reuse_rejected(index):
    first,second,*_=ready(index)
    row=signed(index,first,0,GENESIS,reviewer="same")
    other=signed(index,second,1,digest(row),reviewer="same")
    with pytest.raises(EvidenceError,match="reviewer"):
        queue(index,[row,other])
    other=signed(index,second,1,digest(row),artifact=row["artifact_sha256"])
    with pytest.raises(EvidenceError,match="artifact"):
        queue(index,[row,other])
    with pytest.raises(EvidenceError):
        queue(index,[row,row])
    with pytest.raises(EvidenceError):
        queue(index,[row],expected_head=GENESIS)


def test_receipt_tampering_and_source_change_rejected(index):
    row=signed(index,ready(index)[0],0,GENESIS)
    row["artifact_sha256"]="b"*64
    with pytest.raises(EvidenceError,match="seal"):
        queue(index,[row])
    source=_synthetic_report(runs=2)
    with pytest.raises(EvidenceError):
        load_index(source,expected_source_digest=index.source_digest,authorized=True)


def test_lane_pagination_does_not_change_global_accounting(index):
    a=queue(index,lane="dragon_observation",page_size=3)
    b=queue(index,lane="dragon_observation",page_size=3,page=1)
    assert a["counts"]==b["counts"] and a["filtered_count"]==a["lens_count"]
    assert all(row["lane"]=="dragon_observation" for row in a["rows"]+b["rows"])
    assert not {r["task_id"] for r in a["rows"]}&{r["task_id"] for r in b["rows"]}


def test_nested_index_mutation_is_not_accepted(index):
    from dataclasses import replace
    tasks=deepcopy(index.tasks)
    tasks[0]["material_ready"]=not tasks[0]["material_ready"]
    with pytest.raises(EvidenceError):
        queue(replace(index,tasks=tasks))
