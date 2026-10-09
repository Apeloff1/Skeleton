#!/usr/bin/env python3
"""Fail-closed verifier for the post-P0/P1 masterplan continuation frontier."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from typing import Any,Sequence

ROOT=Path(__file__).resolve().parents[1]
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
CONSTRUCTION=Path("machine/ai_app_construction.json")
P1=Path("machine/ai_p1_terminal_closure.json")
P2=Path("machine/ai_p2_functional_ai_closure.json")
P3_T0=Path("machine/ai_p3_expansion_closure.json")
P3_T1=Path("machine/ai_p3_engineering_closure.json")
P3_T1_MAP=Path("machine/ai_p3_engineering_execution_map.json")
P3_ACTIVE_MAP=Path("machine/ai_p3_execution_map.json")
MASTER=Path("machine/ai_master_plan.json")
STORAGE_CANDIDATE=Path("machine/ai_p3t2_storage_candidate.json")
DATA_CANDIDATE=Path("machine/ai_p3t2_data_candidate.json")
TRAINING_CANDIDATE=Path("machine/ai_p3t2_training_candidate.json")
LEARNING_CANDIDATE=Path("machine/ai_p3t2_learning_candidate.json")
MULTIMODAL_CANDIDATE=Path("machine/ai_p3t2_multimodal_candidate.json")
BRANCH_CANDIDATE="feat/p3t2-training-learning-multimodal-gapfill-20261005"
STORAGE_LANDED_MAIN_SHA="ed7035334243bb60c2b4d231cab4b86ee648ec0c"
DATA_LANDED_MAIN_SHA="573658f64efc0ae8a52e08ddec256f98ce963617"
P0_GAPS={"gap-conversation-state-authority","gap-tool-runtime-convergence","gap-context-compiler-convergence","gap-verification-evidence-contract","gap-provider-interaction-protocol","gap-engine-application-execution-boundary","gap-cognitive-execution-loop","gap-streaming-protocol","gap-governance-registry","gap-memory-durable-authority","gap-state-authority-convergence","gap-cost-admission","gap-e2e-golden-journeys","gap-provider-surface-convergence"}
P1_GAPS={"gap-feedback-promotion","gap-provider-redundancy","gap-release-slo-loop"}
EXPECTED_T2=["VOL-133","VOL-135","VOL-136","VOL-137","VOL-138","VOL-139","VOL-140","VOL-141","VOL-142","VOL-143","VOL-144","VOL-145","VOL-146","VOL-147","VOL-148","VOL-149","VOL-150","VOL-151","VOL-152","VOL-153","VOL-154","VOL-155","VOL-156","VOL-157","VOL-158","VOL-159","VOL-179","VOL-407","VOL-408","VOL-411","VOL-412","VOL-413"]
EXPECTED_NATIVE_TRAINING_CORE=["VOL-133","VOL-135","VOL-136","VOL-137","VOL-138","VOL-139","VOL-140","VOL-141","VOL-142","VOL-143","VOL-144","VOL-145","VOL-146","VOL-147","VOL-148","VOL-149","VOL-150","VOL-151","VOL-152"]

class MasterplanContinuationError(RuntimeError): pass

def _load(root:Path,rel:Path)->dict[str,Any]:
    try:value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise MasterplanContinuationError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise MasterplanContinuationError(f"{rel} must contain an object")
    return value

def _partition(name:str,source:int,scheduled:int,deferred:int)->None:
    if source!=scheduled+deferred: raise MasterplanContinuationError(f"{name} breadth is not conserved: {source} != {scheduled} + {deferred}")

def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve()
    f=_load(root,FRONTIER); construction=_load(root,CONSTRUCTION); p1=_load(root,P1); p2=_load(root,P2)
    t0=_load(root,P3_T0); t1=_load(root,P3_T1); t1m=_load(root,P3_T1_MAP); p3=_load(root,P3_ACTIVE_MAP); master=_load(root,MASTER); storage_candidate=_load(root,STORAGE_CANDIDATE); data_candidate=_load(root,DATA_CANDIDATE); training_candidate=_load(root,TRAINING_CANDIDATE); learning_candidate=_load(root,LEARNING_CANDIDATE); multimodal_candidate=_load(root,MULTIMODAL_CANDIDATE)
    if f.get("schema_version")!="skeleton.ai.masterplan_continuation_frontier.v1": raise MasterplanContinuationError("continuation schema drift")
    if f.get("status")!="active": raise MasterplanContinuationError("continuation frontier must remain active")
    rows=construction.get("gap_register")
    if not isinstance(rows,list): raise MasterplanContinuationError("canonical gap register must be a list")
    gaps={str(x.get("id")):x for x in rows if isinstance(x,dict) and x.get("id")}
    expected=P0_GAPS|P1_GAPS
    if set(gaps)!=expected: raise MasterplanContinuationError("canonical P0/P1 gap identity drift")
    for gid in sorted(expected):
        row=gaps[gid]
        if row.get("status")!="closed": raise MasterplanContinuationError(f"canonical gap reopened: {gid}")
        if isinstance(row.get("outstanding_evidence"),list) and row["outstanding_evidence"]: raise MasterplanContinuationError(f"canonical gap regained outstanding evidence: {gid}")
        progress=row.get("progress")
        if isinstance(progress,dict) and isinstance(progress.get("remaining"),list) and progress["remaining"]: raise MasterplanContinuationError(f"canonical gap regained remaining work: {gid}")
    inv=f.get("closed_foundations",{}).get("canonical_gap_inventory",{})
    if inv.get("p0_gap_count")!=14 or inv.get("p1_gap_count")!=3: raise MasterplanContinuationError("frontier P0/P1 gap counts drift")
    if set(inv.get("p0_gap_ids",[]))!=P0_GAPS or set(inv.get("p1_gap_ids",[]))!=P1_GAPS: raise MasterplanContinuationError("frontier gap identity drift")
    if p1.get("status")!="closed": raise MasterplanContinuationError("P1 terminal frontier is not closed")
    p1f=p1.get("frontier",{})
    if (p1f.get("masterplan_volume_count"),p1f.get("primary_p1_frontier_volume_count"),p1f.get("deferred_to_p2_volume_count"))!=(421,107,314): raise MasterplanContinuationError("P1 terminal 421/107/314 partition drift")
    _partition("P1",421,107,314)
    if p2.get("status")!="closed": raise MasterplanContinuationError("P2 functional frontier is not closed")
    p2s=p2.get("source_scope",{})
    if (p2s.get("p2_volume_count"),p2s.get("scheduled_volume_count"),p2.get("deferred_scope",{}).get("queued_volume_count"))!=(314,57,257): raise MasterplanContinuationError("P2 functional 314/57/257 partition drift")
    _partition("P2",314,57,257)
    if t0.get("status")!="closed": raise MasterplanContinuationError("P3-T0 expansion frontier is not closed")
    t0f=t0.get("frontier",{})
    if t0.get("parent",{}).get("inherited_volume_count")!=257 or (t0f.get("scheduled_volume_count"),t0.get("deferred_scope",{}).get("queued_volume_count"))!=(23,234): raise MasterplanContinuationError("P3-T0 257/23/234 partition drift")
    _partition("P3-T0",257,23,234)
    if t1.get("status")!="closed": raise MasterplanContinuationError("P3-T1 engineering frontier is not closed")
    t1f=t1.get("frontier",{})
    if t1.get("parent",{}).get("source_volume_count")!=234 or (t1f.get("scheduled_volume_count"),t1.get("deferred_scope",{}).get("queued_volume_count"))!=(37,197): raise MasterplanContinuationError("P3-T1 234/37/197 partition drift")
    _partition("P3-T1",234,37,197)
    if p3.get("status")!="active" or p3.get("authority",{}).get("parent_functional_closure")!=str(P2): raise MasterplanContinuationError("canonical P3 execution authority drift")
    canonical=t1m.get("first_tranche",{}).get("queued_volume_refs")
    if not isinstance(canonical,list) or len(canonical)!=197 or len(set(canonical))!=197: raise MasterplanContinuationError("canonical P3-T1 deferred identities drift")
    if f.get("continuation_source",{}).get("volume_refs")!=canonical: raise MasterplanContinuationError("continuation source must equal the exact P3-T1 deferred order")
    t2=f.get("next_tranche",{})
    if t2.get("status")!="planned": raise MasterplanContinuationError("P3-T2 must remain planned")
    scheduled=t2.get("scheduled_volume_refs"); queued=t2.get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list) or len(scheduled)!=32 or len(queued)!=165: raise MasterplanContinuationError("P3-T2 partition must remain 32/165")
    if len(set(scheduled))!=32 or len(set(queued))!=165: raise MasterplanContinuationError("P3-T2 partition contains duplicates")
    if set(scheduled)&set(queued): raise MasterplanContinuationError("P3-T2 scheduled and queued ownership overlaps")
    if set(scheduled)|set(queued)!=set(canonical): raise MasterplanContinuationError("P3-T2 scheduled plus queued refs must preserve the exact 197 source")
    if scheduled!=EXPECTED_T2: raise MasterplanContinuationError("consolidated P3-T2 scheduled identity drift")
    _partition("P3-T2",197,32,165)
    rec=f.get("reconciliation",{}); core=rec.get("native_training_core_volume_refs")
    if core!=EXPECTED_NATIVE_TRAINING_CORE: raise MasterplanContinuationError("native-training core identity drift")
    if not set(core).issubset(set(scheduled)): raise MasterplanContinuationError("native-training core escaped consolidated T2 ownership")
    if rec.get("native_training_core_is_subset_of_t2") is not True: raise MasterplanContinuationError("native-training subset assertion missing")
    owners=t2.get("planned_task_owners")
    if not isinstance(owners,list) or len(owners)!=6 or t2.get("owner_count")!=6: raise MasterplanContinuationError("P3-T2 requires six planned task owners")
    task_ids=[x.get("task_id") for x in owners if isinstance(x,dict)]
    if len(task_ids)!=6 or len(set(task_ids))!=6: raise MasterplanContinuationError("P3-T2 task owner identity drift")
    owned=[]
    seen_tasks=set()
    for task in owners:
        tid=task.get("task_id"); deps=task.get("depends_on"); refs=task.get("primary_volume_refs")
        if task.get("planning_status")!="planned": raise MasterplanContinuationError(f"{tid} planning status must remain planned")
        if task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False or task.get("verification_signed") is not False: raise MasterplanContinuationError(f"{tid} planning owner may not self-complete or self-sign")
        if not isinstance(deps,list) or not set(deps).issubset(seen_tasks): raise MasterplanContinuationError(f"{tid} task dependency order is not forward-safe")
        if not isinstance(refs,list) or not refs: raise MasterplanContinuationError(f"{tid} has no planned volume ownership")
        owned.extend(refs); seen_tasks.add(tid)
    owner_by_id={x.get("task_id"):x for x in owners if isinstance(x,dict)}
    expected_candidates={
        "P3T2-STORAGE-01":{
            "lane_id":"P3T2-L0",
            "kind":"landed",
            "pull_request":2477,
            "merged_main_sha":STORAGE_LANDED_MAIN_SHA,
            "candidate_contract":STORAGE_CANDIDATE,
            "contract":storage_candidate,
        },
        "P3T2-DATA-01":{
            "lane_id":"P3T2-L1",
            "kind":"landed",
            "pull_request":2484,
            "merged_main_sha":DATA_LANDED_MAIN_SHA,
            "candidate_contract":DATA_CANDIDATE,
            "contract":data_candidate,
        },
        "P3T2-TRAINING-01":{
            "lane_id":"P3T2-L2",
            "kind":"branch",
            "candidate_contract":TRAINING_CANDIDATE,
            "contract":training_candidate,
        },
        "P3T2-LEARNING-01":{
            "lane_id":"P3T2-L3",
            "kind":"branch",
            "candidate_contract":LEARNING_CANDIDATE,
            "contract":learning_candidate,
        },
        "P3T2-MULTIMODAL-01":{
            "lane_id":"P3T2-L4",
            "kind":"branch",
            "candidate_contract":MULTIMODAL_CANDIDATE,
            "contract":multimodal_candidate,
        },
    }
    candidate_owners=[x.get("task_id") for x in owners if isinstance(x,dict) and x.get("implementation_candidate") is not None]
    if candidate_owners!=list(expected_candidates): raise MasterplanContinuationError("landed implementation-candidate owner inventory drift (P3-T2 implementation-candidate owner inventory drift)")
    if t2.get("implementation_candidate_count")!=5 or t2.get("branch_implementation_candidate_count")!=3 or t2.get("landed_unpromoted_owner_count")!=0: raise MasterplanContinuationError("P3-T2 implementation-candidate progress counts drift")
    for task_id,spec in expected_candidates.items():
        owner=owner_by_id.get(task_id)
        if not isinstance(owner,dict): raise MasterplanContinuationError(f"{task_id} owner missing")
        meta=owner.get("implementation_candidate")
        if not isinstance(meta,dict): raise MasterplanContinuationError(f"{task_id} implementation-candidate evidence missing")
        expected_meta={
            "candidate_contract":str(spec["candidate_contract"]),
            "candidate_status":"implementation_candidate",
            "exact_head_validation_required":True,
            "exact_head_validation_status":"pending",
            "promotion_authority":False,
        }
        if spec["kind"]=="landed":
            expected_meta.update({
                "status":"landed_pending_exact_head_validation",
                "pull_request":spec["pull_request"],
                "merged_main_sha":spec["merged_main_sha"],
            })
        else:
            expected_meta.update({
                "status":"branch_pending_exact_head_validation",
                "candidate_branch":BRANCH_CANDIDATE,
            })
        for key,value in expected_meta.items():
            if meta.get(key)!=value: raise MasterplanContinuationError(f"{task_id} candidate metadata drift: {key}")
        if spec["kind"]=="landed" and re.fullmatch(r"[0-9a-f]{40}",str(meta.get("merged_main_sha",""))) is None:
            raise MasterplanContinuationError(f"{task_id} merged main SHA is malformed")
        contract=spec["contract"]
        if contract.get("task_id")!=task_id or contract.get("lane_id")!=spec["lane_id"] or contract.get("status")!="implementation_candidate": raise MasterplanContinuationError(f"{task_id} candidate contract identity drift")
        promotion=contract.get("promotion_state",{})
        for key in ("completion_checkbox","implementation_signed","verification_signed","may_self_close"):
            if promotion.get(key) is not False: raise MasterplanContinuationError(f"{task_id} candidate contract illegally promoted {key}")
    if len(owned)!=32 or len(set(owned))!=32: raise MasterplanContinuationError("P3-T2 volume ownership must be exactly one owner per scheduled volume")
    if set(owned)!=set(scheduled): raise MasterplanContinuationError("P3-T2 task ownership must cover the exact scheduled volume set")
    lanes=t2.get("lanes")
    if not isinstance(lanes,list) or len(lanes)!=6: raise MasterplanContinuationError("P3-T2 requires six dependency lanes")
    ids=[x.get("id") for x in lanes if isinstance(x,dict)]
    if len(ids)!=6 or len(set(ids))!=6: raise MasterplanContinuationError("P3-T2 lane identity drift")
    seen=set()
    for lane in lanes:
        deps=lane.get("depends_on")
        if not isinstance(deps,list) or not set(deps).issubset(seen): raise MasterplanContinuationError(f"{lane.get('id')} dependency order is not forward-safe")
        seen.add(lane.get("id"))
    volumes=master.get("volumes")
    if not isinstance(volumes,list) or len(volumes)!=421: raise MasterplanContinuationError("masterplan must remain 421 volumes")
    keys={str(v.get("key")) for v in volumes if isinstance(v,dict) and v.get("key")}
    missing=sorted(set(canonical)-keys)
    if missing: raise MasterplanContinuationError("continuation references unknown masterplan volumes: "+",".join(missing))
    policy=f.get("promotion_policy",{})
    for key in ("next_tranche_may_self_close","planning_may_grant_completion_checkbox","planning_may_grant_implementation_signature","planning_may_grant_verification_signature"):
        if policy.get(key) is not False: raise MasterplanContinuationError(f"unsafe planning authority: {key}")
    for key in ("exact_head_ci_required_for_landed_evidence","independent_closure_authority_required","current_main_reconciliation_required"):
        if policy.get(key) is not True: raise MasterplanContinuationError(f"missing continuation gate: {key}")
    return {"status":"valid","canonical_gap_count":17,"p0_gap_count":14,"p1_gap_count":3,"p1_terminal_closed_volume_count":107,"p2_deferred_volume_count":257,"p3_t0_deferred_volume_count":234,"p3_t1_deferred_volume_count":197,"p3_t2_planned_volume_count":32,"p3_t2_queued_volume_count":165,"native_training_core_volume_count":19,"planned_owner_count":6,"implementation_candidate_count":5,"landed_implementation_candidate_count":2,"branch_implementation_candidate_count":3,"landed_unpromoted_owner_count":0}

def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--json",action="store_true"); args=parser.parse_args(argv)
    try: result=validate(ROOT)
    except MasterplanContinuationError as exc: print(f"masterplan continuation: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else f"masterplan continuation: OK (P0/P1 gaps={result['canonical_gap_count']}, P3-T2={result['p3_t2_planned_volume_count']}/{result['p3_t2_queued_volume_count']})")
    return 0
if __name__=="__main__": raise SystemExit(main())
