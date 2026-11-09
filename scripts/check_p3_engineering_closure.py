#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys,re
from pathlib import Path
from typing import Any,Sequence

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=Path("machine/ai_p3_engineering_closure.json")
MAP=Path("machine/ai_p3_engineering_execution_map.json")
BACKLOG=Path("machine/ai_p3_engineering_task_backlog.json")
PARENT=Path("machine/ai_p3_expansion_closure.json")
INHERITED={"VOL-098","VOL-100","VOL-101","VOL-105"}

class P3EngineeringClosureError(RuntimeError): pass

def _load(root:Path,rel:Path)->dict[str,Any]:
    try:value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise P3EngineeringClosureError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise P3EngineeringClosureError(f"{rel} must contain an object")
    return value

def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve(); closure=_load(root,MANIFEST); ext=_load(root,MAP); backlog=_load(root,BACKLOG); parent=_load(root,PARENT)
    if closure.get("status") not in {"candidate","closed"}: raise P3EngineeringClosureError("closure status must be candidate or closed")
    if closure.get("claim_scope")!="bounded_autonomous_engineering_extension": raise P3EngineeringClosureError("closure claim scope drift")
    if parent.get("status")!="closed": raise P3EngineeringClosureError("T1 closure requires closed P3-T0")
    source=ext.get("source_scope",{}); first=ext.get("first_tranche",{})
    if source.get("expected_volume_count")!=234 or len(source.get("volume_refs",[]))!=234: raise P3EngineeringClosureError("T1 source scope must remain 234")
    scheduled=first.get("scheduled_volume_refs"); queued=first.get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list) or len(scheduled)!=37 or len(queued)!=197: raise P3EngineeringClosureError("T1 closure partition must remain 37/197")
    if set(scheduled)&set(queued) or set(scheduled)|set(queued)!=set(source.get("volume_refs",[])): raise P3EngineeringClosureError("T1 closure partition must preserve source exactly")
    if set(scheduled)&INHERITED: raise P3EngineeringClosureError("T1 closure may not re-own inherited T0 volumes")
    inherited=closure.get("inherited_prerequisites",{}).get("volume_refs",[])
    if set(inherited)!=INHERITED: raise P3EngineeringClosureError("inherited prerequisite identity drift")
    frontier=closure.get("frontier",{})
    if frontier.get("scheduled_volume_count")!=37 or frontier.get("queued_volume_count")!=197 or frontier.get("scheduled_volume_refs")!=scheduled: raise P3EngineeringClosureError("closure frontier drift")
    tasks=backlog.get("tasks")
    if not isinstance(tasks,list) or len(tasks)!=6: raise P3EngineeringClosureError("T1 closure requires six task owners")
    if frontier.get("task_ids")!=[t.get("task_id") for t in tasks]: raise P3EngineeringClosureError("closure task identity drift")
    head = closure.get("evidence_head")
    if closure["status"] == "closed" and (not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head)):
        raise P3EngineeringClosureError("closed T1 requires a valid exact source head")
    for task in tasks:
        tid=task.get("task_id")
        status=task.get("status")
        refs=task.get("evidence_refs")
        if not isinstance(refs,list) or len(refs)<6 or not all(isinstance(ref,str) for ref in refs):
            raise P3EngineeringClosureError(f"{tid} lacks exact-head evidence")
        if closure["status"] == "closed":
            if status != "closed": raise P3EngineeringClosureError(f"{tid} is not signed closed")
            if (task.get("completion_checkbox") is not True or task.get("implementation_signed") is not True
                or task.get("verification_signed") is not True or task.get("completion_checkbox_mark") != "[x]"):
                raise P3EngineeringClosureError(f"{tid} closed task has incomplete signoffs")
            if (f"git-head:{head}" not in refs
                or f"workflow:P3 Engineering Extension Authority@{head}:success" not in refs
                or not any(re.fullmatch(r"github-actions-run:[0-9]+", ref) for ref in refs)):
                raise P3EngineeringClosureError(f"{tid} closed task lacks matching exact-head authority")
        else:
            if status!="landed_unpromoted": raise P3EngineeringClosureError(f"{tid} is not evidence-landed")
            if (task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False
                or task.get("verification_signed") is not False):
                raise P3EngineeringClosureError(f"{tid} may not self-complete or self-sign")
    expected={"task_count":6,"in_progress_count":0,"ready_count":0,"blocked_count":0,"landed_unpromoted_count":0 if closure["status"]=="closed" else 6,"scheduled_volume_count":37,"queued_volume_count":197,"source_volume_count":234}
    if backlog.get("summary")!=expected or ext.get("progress")!=expected: raise P3EngineeringClosureError("T1 terminal progress drift")
    if closure.get("deferred_scope",{}).get("queued_volume_count")!=197: raise P3EngineeringClosureError("T1 closure must preserve 197 deferred volumes")
    if len(closure.get("evidence_refs",[]))<8: raise P3EngineeringClosureError("T1 closure lacks implementation evidence")
    ce=closure.get("closure_evidence")
    if not isinstance(ce,list): raise P3EngineeringClosureError("closure_evidence must be a list")
    if closure.get("status")=="closed":
        if len(ce)<3: raise P3EngineeringClosureError("closed T1 frontier requires exact-head closure evidence")
        closure_heads={ref.removeprefix("git-head:") for ref in ce if isinstance(ref,str) and re.fullmatch(r"git-head:[0-9a-f]{40}",ref)}
        if not closure_heads or not any(f"workflow:P3 Engineering Closure@{c_head}:success" in ce for c_head in closure_heads):
            raise P3EngineeringClosureError("closed T1 frontier requires matching closure workflow evidence")
        if not any(isinstance(ref,str) and re.fullmatch(r"github-actions-run:[0-9]+",ref) for ref in ce):
            raise P3EngineeringClosureError("closed T1 frontier requires an Actions run receipt")
    return {"status":"valid","closure_status":closure["status"],"source_volume_count":234,"scheduled_volume_count":37,"queued_volume_count":197,"landed_task_count":6}

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("--json",action="store_true"); a=p.parse_args(argv)
    try:r=validate(ROOT)
    except P3EngineeringClosureError as exc: print(f"P3 engineering closure: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(r,indent=2,sort_keys=True) if a.json else f"P3 engineering closure: OK ({r['scheduled_volume_count']} landed / {r['queued_volume_count']} deferred)")
    return 0
if __name__=="__main__": raise SystemExit(main())
