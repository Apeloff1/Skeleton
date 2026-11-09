#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any,Sequence
ROOT=Path(__file__).resolve().parents[1]
MAP=Path("machine/ai_p3_learning_execution_map.json");BACKLOG=Path("machine/ai_p3_learning_task_backlog.json")
PARENT_MAP=Path("machine/ai_p3_engineering_execution_map.json");PARENT_CLOSURE=Path("machine/ai_p3_engineering_closure.json");MASTER=Path("machine/ai_master_plan.json")
EXPECTED_TASKS={
"P3T2-STORAGE-01":{"VOL-133","VOL-135","VOL-136"},
"P3T2-DATA-01":{"VOL-137","VOL-138","VOL-139","VOL-140","VOL-141","VOL-142"},
"P3T2-TRAINING-01":{"VOL-143","VOL-144","VOL-145","VOL-146","VOL-147","VOL-148","VOL-149"},
"P3T2-LEARNING-01":{"VOL-150","VOL-151","VOL-152"},
"P3T2-MULTIMODAL-01":{"VOL-153","VOL-154","VOL-155","VOL-156","VOL-157","VOL-158","VOL-159"},
"P3T2-LIFECYCLE-01":{"VOL-179","VOL-407","VOL-408","VOL-411","VOL-412","VOL-413"}}
EXPECTED_DEPS={"P3T2-STORAGE-01":[],"P3T2-DATA-01":["P3T2-STORAGE-01"],"P3T2-TRAINING-01":["P3T2-DATA-01"],"P3T2-LEARNING-01":["P3T2-TRAINING-01"],"P3T2-MULTIMODAL-01":["P3T2-DATA-01","P3T2-TRAINING-01","P3T2-LEARNING-01"],"P3T2-LIFECYCLE-01":["P3T2-TRAINING-01","P3T2-LEARNING-01"]}
INHERITED={"VOL-001","VOL-006","VOL-019","VOL-020","VOL-005","VOL-007","VOL-097","VOL-104"}
class P3LearningValidationError(RuntimeError):pass
def _load(root:Path,rel:Path)->dict[str,Any]:
    try:v=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:raise P3LearningValidationError(f"cannot read {rel}") from exc
    if not isinstance(v,dict):raise P3LearningValidationError(f"{rel} must contain an object")
    return v
def _ob(v):return {"volume_ref":v.get("key"),"title":v.get("title"),"depth_pass":v.get("depth_pass"),"accountability_id":v.get("accountability_id"),"implementation_status":v.get("implementation_status"),"completion_checkbox":v.get("completion_checkbox"),"signing_required":v.get("signing_required"),"contracts":v.get("contracts"),"risks":v.get("risks"),"gaps":v.get("gaps"),"implementation_paths":v.get("implementation_paths"),"tests":v.get("tests"),"evaluations":v.get("evaluations")}
def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve();ext=_load(root,MAP);back=_load(root,BACKLOG);parent=_load(root,PARENT_MAP);closed=_load(root,PARENT_CLOSURE);master=_load(root,MASTER)
    if closed.get("status")!="closed":raise P3LearningValidationError("P3-T2 requires closed P3-T1 engineering frontier")
    pq=parent.get("first_tranche",{}).get("queued_volume_refs")
    if not isinstance(pq,list) or len(pq)!=197:raise P3LearningValidationError("P3-T1 deferred frontier must remain 197 volumes")
    src=ext.get("source_scope",{})
    if src.get("volume_refs")!=pq or src.get("expected_volume_count")!=197:raise P3LearningValidationError("P3-T2 source must exactly equal P3-T1 deferred queue")
    first=ext.get("first_tranche",{});scheduled=first.get("scheduled_volume_refs");queued=first.get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list) or len(scheduled)!=32 or len(queued)!=165:raise P3LearningValidationError("P3-T2 partition must remain 32/165")
    if set(scheduled)&set(queued) or set(scheduled)|set(queued)!=set(pq):raise P3LearningValidationError("P3-T2 partition must preserve parent queue exactly")
    if set(scheduled)&INHERITED:raise P3LearningValidationError("P3-T2 may not re-own inherited prerequisite volumes")
    volumes={v.get("key"):v for v in master.get("volumes",[]) if isinstance(v,dict) and v.get("key")}
    tasks={t.get("task_id"):t for t in back.get("tasks",[]) if isinstance(t,dict) and t.get("task_id")}
    if set(tasks)!=set(EXPECTED_TASKS):raise P3LearningValidationError("P3-T2 task inventory drift")
    landed={tid for tid,t in tasks.items() if t.get("status")=="landed_unpromoted"};owned=[]
    for tid,expected in EXPECTED_TASKS.items():
        t=tasks[tid];refs=t.get("primary_volume_refs")
        if not isinstance(refs,list) or set(refs)!=expected:raise P3LearningValidationError(f"{tid} ownership drift")
        if t.get("depends_on")!=EXPECTED_DEPS[tid]:raise P3LearningValidationError(f"{tid} dependency drift")
        owned.extend(refs);status=t.get("status")
        if status not in {"blocked","ready","in_progress","landed_unpromoted","closed"}:raise P3LearningValidationError(f"{tid} unsupported status")
        unresolved=[dep for dep in t.get("depends_on",[]) if dep not in landed]
        if status=="blocked" and not unresolved:raise P3LearningValidationError(f"{tid} blocked with all dependencies landed")
        if status in {"ready","in_progress","landed_unpromoted"} and unresolved:raise P3LearningValidationError(f"{tid} has unresolved dependencies")
        if t.get("status") != "closed" and (t.get("completion_checkbox") is not False or t.get("implementation_signed") is not False or t.get("verification_signed") is not False):raise P3LearningValidationError(f"{tid} may not self-complete or self-sign unless closed")
        obs=t.get("masterplan_obligations")
        if not isinstance(obs,list) or len(obs)!=len(refs):raise P3LearningValidationError(f"{tid} obligation coverage drift")
        om={o.get("volume_ref"):o for o in obs if isinstance(o,dict)}
        for ref in refs:
            if ref not in volumes or om.get(ref)!=_ob(volumes[ref]):raise P3LearningValidationError(f"{tid} narrows/drifts masterplan obligation {ref}")
    if len(owned)!=32 or len(set(owned))!=32 or set(owned)!=set(scheduled):raise P3LearningValidationError("P3-T2 scheduled volumes require exactly one owner")
    summary={"task_count":6,"in_progress_count":sum(t.get("status")=="in_progress" for t in tasks.values()),"ready_count":sum(t.get("status")=="ready" for t in tasks.values()),"blocked_count":sum(t.get("status")=="blocked" for t in tasks.values()),"landed_unpromoted_count":sum(t.get("status")=="landed_unpromoted" for t in tasks.values()),"scheduled_volume_count":32,"queued_volume_count":165,"source_volume_count":197}
    if back.get("summary")!=summary or ext.get("progress")!=summary:raise P3LearningValidationError("P3-T2 progress projection drift")
    return {"status":"valid",**summary,"parent_closure":"closed"}
def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--json",action="store_true");a=p.parse_args(argv)
    try:r=validate(ROOT)
    except P3LearningValidationError as exc:print(f"P3 learning execution map: FAIL: {exc}",file=sys.stderr);return 1
    print(json.dumps(r,indent=2,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
