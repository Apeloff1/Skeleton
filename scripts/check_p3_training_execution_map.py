#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Sequence

ROOT=Path(__file__).resolve().parents[1]
MAP=Path("machine/ai_p3_training_execution_map.json")
BACKLOG=Path("machine/ai_p3_training_task_backlog.json")
PARENT_MAP=Path("machine/ai_p3_engineering_execution_map.json")
PARENT_CLOSURE=Path("machine/ai_p3_engineering_closure.json")
MASTER=Path("machine/ai_master_plan.json")

EXPECTED_TASKS={
    "P3T-DATA-01": {"VOL-133","VOL-135","VOL-136","VOL-137","VOL-138","VOL-139","VOL-140","VOL-141","VOL-142"},
    "P3T-TRAIN-01": {"VOL-143","VOL-144","VOL-145","VOL-146","VOL-147"},
    "P3T-EVAL-01": {"VOL-148","VOL-152"},
    "P3T-POST-01": {"VOL-149","VOL-150","VOL-151"},
}
EXPECTED_DEPS={
    "P3T-DATA-01": [],
    "P3T-TRAIN-01": ["P3T-DATA-01"],
    "P3T-EVAL-01": ["P3T-TRAIN-01"],
    "P3T-POST-01": ["P3T-TRAIN-01","P3T-EVAL-01"],
}

class P3TrainingValidationError(RuntimeError): pass

def _load(root:Path,rel:Path)->dict[str,Any]:
    try:value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise P3TrainingValidationError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise P3TrainingValidationError(f"{rel} must contain an object")
    return value

def _expected_obligation(volume:dict[str,Any])->dict[str,Any]:
    return {
        "volume_ref":volume.get("key"),"title":volume.get("title"),"depth_pass":volume.get("depth_pass"),
        "accountability_id":volume.get("accountability_id"),"implementation_status":volume.get("implementation_status"),
        "completion_checkbox":volume.get("completion_checkbox"),"signing_required":volume.get("signing_required"),
        "contracts":volume.get("contracts"),"risks":volume.get("risks"),"gaps":volume.get("gaps"),
        "implementation_paths":volume.get("implementation_paths"),"tests":volume.get("tests"),"evaluations":volume.get("evaluations"),
    }

def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve()
    ext=_load(root,MAP); backlog=_load(root,BACKLOG); parent=_load(root,PARENT_MAP); closure=_load(root,PARENT_CLOSURE); master=_load(root,MASTER)
    if closure.get("status")!="closed": raise P3TrainingValidationError("P3-T2 requires closed P3-T1 engineering frontier")
    parent_queue=parent.get("first_tranche",{}).get("queued_volume_refs")
    if not isinstance(parent_queue,list) or len(parent_queue)!=197: raise P3TrainingValidationError("P3-T1 deferred frontier must remain 197 volumes")
    source=ext.get("source_scope",{})
    if source.get("volume_refs")!=parent_queue or source.get("expected_volume_count")!=197: raise P3TrainingValidationError("P3-T2 source must exactly equal P3-T1 deferred queue")
    first=ext.get("first_tranche",{}); scheduled=first.get("scheduled_volume_refs"); queued=first.get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list) or len(scheduled)!=19 or len(queued)!=178: raise P3TrainingValidationError("P3-T2 partition must remain 19/178")
    if set(scheduled)&set(queued) or set(scheduled)|set(queued)!=set(parent_queue): raise P3TrainingValidationError("P3-T2 partition must preserve parent queue exactly")
    volumes={v.get("key"):v for v in master.get("volumes",[]) if isinstance(v,dict) and v.get("key")}
    tasks={t.get("task_id"):t for t in backlog.get("tasks",[]) if isinstance(t,dict) and t.get("task_id")}
    if set(tasks)!=set(EXPECTED_TASKS): raise P3TrainingValidationError("P3-T2 task inventory drift")
    landed={tid for tid,t in tasks.items() if t.get("status")=="landed_unpromoted"}
    owned=[]
    for tid,expected in EXPECTED_TASKS.items():
        task=tasks[tid]; refs=task.get("primary_volume_refs")
        if not isinstance(refs,list) or set(refs)!=expected: raise P3TrainingValidationError(f"{tid} ownership drift")
        if task.get("depends_on")!=EXPECTED_DEPS[tid]: raise P3TrainingValidationError(f"{tid} dependency drift")
        owned.extend(refs)
        status=task.get("status")
        if status not in {"blocked","ready","in_progress","landed_unpromoted"}: raise P3TrainingValidationError(f"{tid} unsupported status")
        unresolved=[dep for dep in task.get("depends_on",[]) if dep not in landed]
        if status=="blocked" and not unresolved: raise P3TrainingValidationError(f"{tid} blocked with all dependencies landed")
        if status in {"ready","in_progress","landed_unpromoted"} and unresolved: raise P3TrainingValidationError(f"{tid} has unresolved dependencies")
        if task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
            raise P3TrainingValidationError(f"{tid} may not self-complete or self-sign")
        obligations=task.get("masterplan_obligations")
        if not isinstance(obligations,list) or len(obligations)!=len(refs): raise P3TrainingValidationError(f"{tid} obligation coverage drift")
        by_ref={o.get("volume_ref"):o for o in obligations if isinstance(o,dict)}
        for ref in refs:
            if ref not in volumes or by_ref.get(ref)!=_expected_obligation(volumes[ref]): raise P3TrainingValidationError(f"{tid} narrows/drifts masterplan obligation {ref}")
    if len(owned)!=19 or len(set(owned))!=19 or set(owned)!=set(scheduled): raise P3TrainingValidationError("P3-T2 scheduled volumes require exactly one owner")
    summary={
        "task_count":4,
        "in_progress_count":sum(t.get("status")=="in_progress" for t in tasks.values()),
        "ready_count":sum(t.get("status")=="ready" for t in tasks.values()),
        "blocked_count":sum(t.get("status")=="blocked" for t in tasks.values()),
        "landed_unpromoted_count":sum(t.get("status")=="landed_unpromoted" for t in tasks.values()),
        "scheduled_volume_count":19,"queued_volume_count":178,"source_volume_count":197,
    }
    if backlog.get("summary")!=summary or ext.get("progress")!=summary: raise P3TrainingValidationError("P3-T2 progress projection drift")
    return {"status":"valid",**summary,"parent_closure":"closed"}

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--json",action="store_true");a=p.parse_args(argv)
    try:r=validate(ROOT)
    except P3TrainingValidationError as exc:
        print(f"P3 training execution map: FAIL: {exc}",file=sys.stderr);return 1
    print(json.dumps(r,indent=2,sort_keys=True) if a.json else f"P3 training execution map: OK ({r['scheduled_volume_count']} scheduled / {r['queued_volume_count']} queued)")
    return 0
if __name__=="__main__": raise SystemExit(main())
