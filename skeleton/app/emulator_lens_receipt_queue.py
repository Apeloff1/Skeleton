"""Authenticate lane-scoped local receipt metadata; never infer physical execution."""
from __future__ import annotations

import hashlib
import hmac
from collections import Counter

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, integer, text, digest, canonical, pin, seal, HEX,
)
from skeleton.app.emulator_lens_work_index import WorkIndex, LANES, MAX_TASKS

GENESIS="0"*64
OUTCOMES=("observed","counterexample","inconclusive","blocked")


def _sha(v):
    if type(v) is not str or not HEX.fullmatch(v):
        raise EvidenceError("SHA-256 metadata required")
    return v


def _keys(keys):
    if type(keys) is not dict or set(keys)!=set(LANES):
        raise EvidenceError("all three scoped review authorities required")
    if any(type(v) is not bytes or not 32<=len(v)<=128 for v in keys.values()):
        raise EvidenceError("invalid local lane key")
    if len(set(keys.values()))!=len(LANES):
        raise EvidenceError("independent lane key material required")


def receipt_body(raw,task,index):
    fields(raw,{"schema","index_digest","task_id","lane","review_id","source_report_digest",
                "catalog_digest","source_receipt_set_digest","outcome","artifact_sha256",
                "consent_scope_sha256","reviewer_id","sequence","previous","signature"})
    if raw["schema"]!="skeleton.emulator-lens-work-receipt.v1":
        raise EvidenceError("unknown receipt schema")
    for k,v in {"index_digest":index.identity,"task_id":task["task_id"],
                "lane":task["lane"],"review_id":task["review_id"],
                "source_report_digest":index.source_digest,"catalog_digest":index.catalog_digest,
                "source_receipt_set_digest":task["source_receipt_set_digest"]}.items():
        if raw[k]!=v:
            raise EvidenceError("receipt source, task or lane mismatch")
    if not task["material_ready"]:
        raise EvidenceError("insufficient source runs for review receipt")
    if raw["outcome"] not in OUTCOMES:
        raise EvidenceError("unknown submitted review state")
    if task["lane"]!="adversarial_review" and raw["outcome"]=="counterexample":
        raise EvidenceError("counterexample must use independent adversarial lane")
    _sha(raw["artifact_sha256"])
    # Consent metadata is required for every lane, including replay.
    _sha(raw["consent_scope_sha256"])
    text(raw["reviewer_id"],96)
    integer(raw["sequence"],0,MAX_TASKS-1)
    _sha(raw["previous"])
    _sha(raw["signature"])
    return {k:v for k,v in raw.items() if k!="signature"}


def reconcile(index,receipts,*,keys,expected_head,authorized):
    if authorized is not True:
        raise PermissionError("explicit local review receipt operator required")
    if not isinstance(index,WorkIndex):
        raise EvidenceError("canonical work index required")
    _keys(keys)
    _sha(expected_head)
    known=index.by_identity
    by_task={}
    by_reviewer={}
    artifact_lanes={}
    prior=GENESIS
    for sequence,raw in enumerate(array(receipts,0,len(known))):
        if type(raw) is not dict or type(raw.get("task_id")) is not str:
            raise EvidenceError("malformed review receipt")
        task=known.get(raw["task_id"])
        if task is None or task["task_id"] in by_task:
            raise EvidenceError("unknown or duplicate review receipt")
        body=receipt_body(raw,task,index)
        if body["sequence"]!=sequence or body["previous"]!=prior:
            raise EvidenceError("review receipt order or predecessor mismatch")
        expected=hmac.new(keys[task["lane"]],canonical(body),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,raw["signature"]):
            raise EvidenceError("lane authorization seal mismatch")
        # Key domains are separate, and submitted reviewer identities cannot
        # stand in for the other actors within one lens review.
        reviewer=(task["review_id"],body["reviewer_id"])
        if reviewer in by_reviewer and by_reviewer[reviewer]!=task["lane"]:
            raise EvidenceError("same reviewer declared for independent lanes")
        artifact=(task["review_id"],body["artifact_sha256"])
        if artifact in artifact_lanes and artifact_lanes[artifact]!=task["lane"]:
            raise EvidenceError("same evidence artifact claimed by independent lanes")
        by_reviewer[reviewer]=task["lane"]
        artifact_lanes[artifact]=task["lane"]
        prior=digest(raw)
        by_task[task["task_id"]]={"outcome":body["outcome"],"receipt_digest":prior,
                                  "artifact_sha256":body["artifact_sha256"]}
    pin(prior,expected_head)
    return by_task,prior


def page_queue(index,receipts,*,keys,expected_head,authorized,page=0,page_size=64,lane=None):
    integer(page,0,MAX_TASKS)
    integer(page_size,1,256)
    if lane is not None and lane not in LANES:
        raise EvidenceError("unknown work lane")
    claims,head=reconcile(index,receipts,keys=keys,expected_head=expected_head,authorized=authorized)
    rows=[]
    counts=Counter()
    lanes={name:Counter() for name in LANES}
    for task in index.tasks:
        claim=claims.get(task["task_id"])
        state=("insufficient_material" if not task["material_ready"] else
               "awaiting_submission" if claim is None else "signed_metadata_"+claim["outcome"])
        counts[state]+=1
        lanes[task["lane"]][state]+=1
        if lane is None or task["lane"]==lane:
            rows.append({**task,"submission_state":state,"submission":claim,
                         "independent_execution_verified":False})
    # Counterexamples first, then insufficient evidence, then pending material.
    priority={"signed_metadata_counterexample":0,"insufficient_material":1,
              "signed_metadata_blocked":2,"signed_metadata_inconclusive":3,
              "awaiting_submission":4,"signed_metadata_observed":5}
    rows.sort(key=lambda x:(priority[x["submission_state"]],x["family"],x["lens_key"],x["lane"]))
    start=page*page_size
    selected=rows[start:start+page_size]
    return seal({"schema":"skeleton.emulator-lens-work-queue.report.v1",
                 "index_digest":index.identity,"source_report_digest":index.source_digest,
                 "catalog_digest":index.catalog_digest,"campaign_audit_digest":index.campaign_audit_digest,
                 "submission_head":head,"task_count":len(index.tasks),
                 "lens_count":len(index.tasks)//len(LANES),"counts":dict(sorted(counts.items())),
                 "lane_counts":{k:dict(sorted(v.items())) for k,v in lanes.items()},
                 "filtered_count":len(rows),"page":page,"page_size":page_size,
                 "next_page":page+1 if start+len(selected)<len(rows) else None,"rows":selected,
                 "signed_receipt_count":len(claims),"independent_native_replay_verified":False,
                 "independent_dragon_observations_verified":0,
                 "independent_adversarial_reviews_verified":0,"native_artifact_bytes_checked":False,
                 "semantic_triangulation_completed":False,"model_weights_updated":False,
                 "production_model_promotion_authorized":False,"release_certified":False})
