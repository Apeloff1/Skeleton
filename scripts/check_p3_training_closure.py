#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any,Sequence

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=Path("machine/ai_p3_training_closure.json")
MAP=Path("machine/ai_p3_training_execution_map.json")
BACKLOG=Path("machine/ai_p3_training_task_backlog.json")
PARENT=Path("machine/ai_p3_engineering_closure.json")

class P3TrainingClosureError(RuntimeError): pass

def _load(root:Path,rel:Path)->dict[str,Any]:
    try:value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise P3TrainingClosureError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise P3TrainingClosureError(f"{rel} must contain an object")
    return value

def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve(); closure=_load(root,MANIFEST); ext=_load(root,MAP); backlog=_load(root,BACKLOG); parent=_load(root,PARENT)
    if closure.get("status") not in {"candidate","closed"}: raise P3TrainingClosureError("closure status must be candidate or closed")
    if closure.get("claim_scope")!="bounded_native_training_and_model_improvement": raise P3TrainingClosureError("closure claim scope drift")
    if parent.get("status")!="closed": raise P3TrainingClosureError("P3-T2 requires closed P3-T1")
    source=ext.get("source_scope",{}); first=ext.get("first_tranche",{})
    if source.get("expected_volume_count")!=197 or len(source.get("volume_refs",[]))!=197: raise P3TrainingClosureError("T2 source scope must remain 197")
    scheduled=first.get("scheduled_volume_refs"); queued=first.get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list) or len(scheduled)!=19 or len(queued)!=178: raise P3TrainingClosureError("T2 closure partition must remain 19/178")
    if set(scheduled)&set(queued) or set(scheduled)|set(queued)!=set(source.get("volume_refs",[])): raise P3TrainingClosureError("T2 closure partition must preserve source exactly")
    frontier=closure.get("frontier",{})
    if frontier.get("scheduled_volume_count")!=19 or frontier.get("queued_volume_count")!=178 or frontier.get("scheduled_volume_refs")!=scheduled: raise P3TrainingClosureError("closure frontier drift")
    tasks=backlog.get("tasks")
    if not isinstance(tasks,list) or len(tasks)!=4: raise P3TrainingClosureError("T2 closure requires four task owners")
    if frontier.get("task_ids")!=[t.get("task_id") for t in tasks]: raise P3TrainingClosureError("closure task identity drift")
    owned=[]
    for task in tasks:
        tid=task.get("task_id"); owned.extend(task.get("primary_volume_refs",[]))
        if task.get("status")!="landed_unpromoted": raise P3TrainingClosureError(f"{tid} is not evidence-landed")
        if task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False or task.get("verification_signed") is not False: raise P3TrainingClosureError(f"{tid} may not self-complete or self-sign")
        evidence=task.get("evidence_refs")
        if not isinstance(evidence,list) or len(evidence)<8: raise P3TrainingClosureError(f"{tid} lacks exact-head evidence")
        if not any(str(x).startswith("workflow:P3 Native Training Acceptance@") for x in evidence): raise P3TrainingClosureError(f"{tid} lacks aggregate training acceptance evidence")
    if len(owned)!=19 or len(set(owned))!=19 or set(owned)!=set(scheduled): raise P3TrainingClosureError("closure ownership drift")
    expected={"task_count":4,"in_progress_count":0,"ready_count":0,"blocked_count":0,"landed_unpromoted_count":4,"scheduled_volume_count":19,"queued_volume_count":178,"source_volume_count":197}
    if backlog.get("summary")!=expected or ext.get("progress")!=expected: raise P3TrainingClosureError("T2 terminal progress drift")
    deferred=closure.get("deferred_scope",{})
    if deferred.get("queued_volume_count")!=178 or deferred.get("queued_volume_refs")!=queued: raise P3TrainingClosureError("T2 closure must preserve exact 178-volume deferred queue")
    requirements=closure.get("requirements",{})
    if requirements.get("production_model_promotion_authorized") is not False: raise P3TrainingClosureError("T2 closure cannot grant production promotion authority")
    for _,path in closure.get("executable_surfaces",{}).items():
        if not isinstance(path,str) or not (root/path).is_file(): raise P3TrainingClosureError(f"missing executable surface: {path}")
    if len(closure.get("evidence_refs",[]))<8: raise P3TrainingClosureError("T2 closure lacks implementation evidence")
    ce=closure.get("closure_evidence")
    if not isinstance(ce,list): raise P3TrainingClosureError("closure_evidence must be a list")
    if closure.get("status")=="closed":
        if len(ce)<3: raise P3TrainingClosureError("closed T2 frontier requires exact-head closure evidence")
        if not any(str(x).startswith("workflow:P3 Training Closure@") for x in ce): raise P3TrainingClosureError("closed T2 frontier requires closure workflow evidence")
    return {"status":"valid","closure_status":closure["status"],"source_volume_count":197,"scheduled_volume_count":19,"queued_volume_count":178,"landed_task_count":4,"production_promotion_authorized":False}

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--json",action="store_true");a=p.parse_args(argv)
    try:r=validate(ROOT)
    except P3TrainingClosureError as exc: print(f"P3 training closure: FAIL: {exc}",file=sys.stderr);return 1
    print(json.dumps(r,indent=2,sort_keys=True) if a.json else f"P3 training closure: OK ({r['scheduled_volume_count']} landed / {r['queued_volume_count']} deferred)")
    return 0
if __name__=="__main__": raise SystemExit(main())
