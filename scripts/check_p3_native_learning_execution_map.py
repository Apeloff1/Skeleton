#!/usr/bin/env python3
"""Validate the stacked P3-T2 Native Learning & Research authority."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
MAP=Path("machine/ai_p3_native_learning_execution_map.json")
BACKLOG=Path("machine/ai_p3_native_learning_task_backlog.json")
PLAN=Path("machine/ai_p3_tranche2_plan.json")
PARENT_MAP=Path("machine/ai_p3_engineering_execution_map.json")
PARENT_CLOSURE=Path("machine/ai_p3_engineering_closure.json")
MASTER=Path("machine/ai_master_plan.json")

class P3NativeLearningError(RuntimeError): pass

def _load(root:Path,rel:Path)->dict[str,Any]:
    try: value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise P3NativeLearningError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise P3NativeLearningError(f"{rel} must contain an object")
    return value

def _dups(values:list[str])->list[str]:
    seen=set(); dup=[]
    for value in values:
        if value in seen and value not in dup: dup.append(value)
        seen.add(value)
    return dup

def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve()
    m=_load(root,MAP); b=_load(root,BACKLOG); p=_load(root,PLAN)
    parent=_load(root,PARENT_MAP); close=_load(root,PARENT_CLOSURE); master=_load(root,MASTER)
    if close.get("status")!="closed": raise P3NativeLearningError("parent engineering closure must be closed")
    source=list(m.get("source_scope",{}).get("volume_refs",[]))
    expected=list(parent.get("first_tranche",{}).get("queued_volume_refs",[]))
    if len(source)!=197 or source!=expected: raise P3NativeLearningError("P3-T2 source must equal parent 197-volume queue")
    scheduled=list(m.get("first_tranche",{}).get("scheduled_volume_refs",[]))
    queued=list(m.get("first_tranche",{}).get("queued_volume_refs",[]))
    if _dups(scheduled) or _dups(queued): raise P3NativeLearningError("duplicate partition refs")
    if set(scheduled)&set(queued): raise P3NativeLearningError("scheduled/queued overlap")
    if set(scheduled)|set(queued)!=set(source): raise P3NativeLearningError("scheduled+queued must cover source exactly")
    if len(scheduled)!=52 or len(queued)!=145: raise P3NativeLearningError("P3-T2 partition must be 52 scheduled / 145 queued")
    tasks=b.get("tasks",[])
    if not isinstance(tasks,list) or len(tasks)!=7: raise P3NativeLearningError("P3-T2 requires seven task owners")
    task_ids=[t.get("task_id") for t in tasks]
    if len(set(task_ids))!=len(task_ids): raise P3NativeLearningError("duplicate task ids")
    owned=[]
    by_id={t["task_id"]:t for t in tasks}
    for task in tasks:
        refs=list(task.get("primary_volume_refs",[])); owned.extend(refs)
        if task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
            raise P3NativeLearningError(f"{task['task_id']} may not self-complete/sign")
        for dep in task.get("depends_on",[]):
            if dep not in by_id: raise P3NativeLearningError(f"{task['task_id']} depends on unknown task {dep}")
        obligations=task.get("masterplan_obligations",[])
        if [o.get("volume_ref") for o in obligations]!=refs:
            raise P3NativeLearningError(f"{task['task_id']} obligation ownership drift")
    if len(owned)!=52 or set(owned)!=set(scheduled) or _dups(owned):
        raise P3NativeLearningError("scheduled volumes require exactly one task owner")
    master_by={v.get("key"):v for v in master.get("volumes",[]) if isinstance(v,dict)}
    fields=("title","depth_pass","accountability_id","implementation_status","completion_checkbox","signing_required","requirements","capabilities","contracts","risks","gaps","implementation_paths","tests","evaluations","evidence")
    for task in tasks:
        for row in task["masterplan_obligations"]:
            ref=row["volume_ref"]; canonical=master_by.get(ref)
            if not canonical: raise P3NativeLearningError(f"unknown masterplan volume {ref}")
            for field in fields:
                expected_value=canonical.get(field,[] if field in {"requirements","capabilities","contracts","risks","gaps","implementation_paths","tests","evaluations","evidence"} else None)
                if row.get(field)!=expected_value:
                    raise P3NativeLearningError(f"{ref}.{field} narrows/drifts masterplan")
    statuses=[t.get("status") for t in tasks]
    if statuses.count("ready")!=1 or statuses.count("blocked")!=6:
        raise P3NativeLearningError("initial P3-T2 status must be one ready / six blocked")
    progress=m.get("progress",{})
    if progress!={"task_count":7,"in_progress_count":0,"ready_count":1,"blocked_count":6,"landed_unpromoted_count":0,"scheduled_volume_count":52,"queued_volume_count":145,"source_volume_count":197}:
        raise P3NativeLearningError("P3-T2 progress drift")
    if p.get("selection",{}).get("selected_volume_refs")!=scheduled:
        raise P3NativeLearningError("P3-T2 plan selection drift")
    return {"status":"valid","source_volume_count":197,"scheduled_volume_count":52,"queued_volume_count":145,"task_count":7}

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--json",action="store_true"); args=parser.parse_args()
    try: result=validate(ROOT)
    except P3NativeLearningError as exc:
        print(f"P3 native learning authority: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,sort_keys=True) if args.json else "P3 native learning authority: OK (52 scheduled / 145 queued)")
    return 0

if __name__=="__main__": raise SystemExit(main())
