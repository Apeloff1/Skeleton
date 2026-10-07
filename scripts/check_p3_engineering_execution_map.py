#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, Sequence

ROOT=Path(__file__).resolve().parents[1]
MAP=Path("machine/ai_p3_engineering_execution_map.json")
BACKLOG=Path("machine/ai_p3_engineering_task_backlog.json")
PARENT_MAP=Path("machine/ai_p3_execution_map.json")
PARENT_CLOSURE=Path("machine/ai_p3_expansion_closure.json")
MASTER=Path("machine/ai_master_plan.json")
EXPECTED_TASKS={
    "P3-WORKFLOW-01": set(["VOL-306","VOL-307","VOL-308","VOL-309","VOL-310","VOL-311","VOL-312","VOL-313","VOL-314","VOL-315","VOL-316"]),
    "P3-AUTONOMY-01": set(["VOL-317","VOL-319"]),
    "P3-CHANGE-01": set(["VOL-330","VOL-331","VOL-332","VOL-333","VOL-334","VOL-335","VOL-336","VOL-337","VOL-338"]),
    "P3-TOOLS-01": set(["VOL-339","VOL-340","VOL-371","VOL-372","VOL-373","VOL-374","VOL-375","VOL-376","VOL-377"]),
    "P3-EFFECTS-01": set(["VOL-378","VOL-379","VOL-380"]),
    "P3-AGENT-01": set(["VOL-203","VOL-204","VOL-206"]),
}
EXPECTED_DEPS={
    "P3-WORKFLOW-01": [],
    "P3-AUTONOMY-01": [
        "P3-WORKFLOW-01"
    ],
    "P3-CHANGE-01": [
        "P3-WORKFLOW-01"
    ],
    "P3-TOOLS-01": [
        "P3-AUTONOMY-01",
        "P3-CHANGE-01"
    ],
    "P3-EFFECTS-01": [
        "P3-TOOLS-01"
    ],
    "P3-AGENT-01": [
        "P3-WORKFLOW-01",
        "P3-AUTONOMY-01",
        "P3-CHANGE-01",
        "P3-TOOLS-01",
        "P3-EFFECTS-01"
    ]
}
INHERITED_ONLY={"VOL-098","VOL-100","VOL-101","VOL-105"}

class P3EngineeringValidationError(RuntimeError): pass

def _load(root:Path,rel:Path)->dict[str,Any]:
    try: value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise P3EngineeringValidationError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise P3EngineeringValidationError(f"{rel} must contain an object")
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
    root=root.resolve(); ext=_load(root,MAP); backlog=_load(root,BACKLOG); parent=_load(root,PARENT_MAP); closure=_load(root,PARENT_CLOSURE); master=_load(root,MASTER)
    if closure.get("status")!="closed": raise P3EngineeringValidationError("P3-T1 requires closed P3-T0 expansion")
    parent_queue=parent.get("first_tranche",{}).get("queued_volume_refs")
    if not isinstance(parent_queue,list) or len(parent_queue)!=234: raise P3EngineeringValidationError("P3-T0 deferred frontier must remain 234 volumes")
    source=ext.get("source_scope",{})
    if source.get("volume_refs")!=parent_queue or source.get("expected_volume_count")!=234: raise P3EngineeringValidationError("P3-T1 source must exactly equal P3-T0 deferred queue")
    first=ext.get("first_tranche",{}); scheduled=first.get("scheduled_volume_refs"); queued=first.get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list) or len(scheduled)!=37 or len(queued)!=197: raise P3EngineeringValidationError("P3-T1 partition must remain 37/197")
    if set(scheduled)&set(queued) or set(scheduled)|set(queued)!=set(parent_queue): raise P3EngineeringValidationError("P3-T1 partition must preserve parent queue exactly")
    if set(scheduled)&INHERITED_ONLY: raise P3EngineeringValidationError("P3-T1 may not re-own P3-T0 prerequisite volumes")
    volumes={v.get("key"):v for v in master.get("volumes",[]) if isinstance(v,dict) and v.get("key")}
    tasks={t.get("task_id"):t for t in backlog.get("tasks",[]) if isinstance(t,dict) and t.get("task_id")}
    if set(tasks)!=set(EXPECTED_TASKS): raise P3EngineeringValidationError("P3-T1 task inventory drift")
    landed={tid for tid,t in tasks.items() if t.get("status")=="landed_unpromoted"}; owned=[]
    for tid,expected in EXPECTED_TASKS.items():
        task=tasks[tid]; refs=task.get("primary_volume_refs")
        if not isinstance(refs,list) or set(refs)!=expected: raise P3EngineeringValidationError(f"{tid} ownership drift")
        if task.get("depends_on")!=EXPECTED_DEPS[tid]: raise P3EngineeringValidationError(f"{tid} dependency drift")
        if set(refs)&INHERITED_ONLY: raise P3EngineeringValidationError(f"{tid} re-owns inherited P3-T0 volume")
        owned.extend(refs); status=task.get("status")
        if status not in {"blocked","ready","in_progress","landed_unpromoted"}: raise P3EngineeringValidationError(f"{tid} unsupported status")
        unresolved=[dep for dep in task.get("depends_on",[]) if dep not in landed]
        if status=="blocked" and not unresolved: raise P3EngineeringValidationError(f"{tid} blocked with all dependencies landed")
        if status in {"ready","in_progress","landed_unpromoted"} and unresolved: raise P3EngineeringValidationError(f"{tid} has unresolved dependencies")
        if task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False or task.get("verification_signed") is not False: raise P3EngineeringValidationError(f"{tid} may not self-complete or self-sign")
        obligations=task.get("masterplan_obligations")
        if not isinstance(obligations,list) or len(obligations)!=len(refs): raise P3EngineeringValidationError(f"{tid} obligation coverage drift")
        by_ref={o.get("volume_ref"):o for o in obligations if isinstance(o,dict)}
        for ref in refs:
            if ref not in volumes or by_ref.get(ref)!=_expected_obligation(volumes[ref]): raise P3EngineeringValidationError(f"{tid} narrows/drifts masterplan obligation {ref}")
    if len(owned)!=37 or len(set(owned))!=37 or set(owned)!=set(scheduled): raise P3EngineeringValidationError("P3-T1 scheduled volumes require exactly one owner")
    summary={
        "task_count":6,
        "in_progress_count":sum(t.get("status")=="in_progress" for t in tasks.values()),
        "ready_count":sum(t.get("status")=="ready" for t in tasks.values()),
        "blocked_count":sum(t.get("status")=="blocked" for t in tasks.values()),
        "landed_unpromoted_count":sum(t.get("status")=="landed_unpromoted" for t in tasks.values()),
        "scheduled_volume_count":37,"queued_volume_count":197,"source_volume_count":234,
    }
    if backlog.get("summary")!=summary or ext.get("progress")!=summary: raise P3EngineeringValidationError("P3-T1 progress projection drift")
    if set(ext.get("inherited_prerequisites",{}).get("volume_refs",[]))!=INHERITED_ONLY: raise P3EngineeringValidationError("P3-T1 inherited prerequisite identity drift")
    return {"status":"valid",**summary,"parent_closure":"closed"}

def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--json",action="store_true"); args=parser.parse_args(argv)
    try: result=validate(ROOT)
    except P3EngineeringValidationError as exc:
        print(f"P3 engineering execution map: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else f"P3 engineering execution map: OK ({result['scheduled_volume_count']} scheduled / {result['queued_volume_count']} queued)")
    return 0

if __name__=="__main__": raise SystemExit(main())
