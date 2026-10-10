#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from typing import Any,Sequence
ROOT=Path(__file__).resolve().parents[1]
CLOSURE=Path("machine/ai_p3_learning_closure.json");MAP=Path("machine/ai_p3_learning_execution_map.json");BACKLOG=Path("machine/ai_p3_learning_task_backlog.json");PARENT=Path("machine/ai_p3_engineering_closure.json")
EXPECTED={"P3T2-STORAGE-01":"P3 Data Foundation","P3T2-DATA-01":"P3 Data Foundation","P3T2-TRAINING-01":"P3 Training Control","P3T2-LEARNING-01":"P3 Learning Programs","P3T2-MULTIMODAL-01":"P3 Multimodal Foundation","P3T2-LIFECYCLE-01":"P3 Model Lifecycle"}
class P3LearningClosureError(RuntimeError):pass
def _load(root:Path,rel:Path)->dict[str,Any]:
    try:v=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:raise P3LearningClosureError(f"cannot read {rel}") from exc
    if not isinstance(v,dict):raise P3LearningClosureError(f"{rel} must contain an object")
    return v
def validate(root:Path=ROOT)->dict[str,Any]:
    root=root.resolve();c=_load(root,CLOSURE);mp=_load(root,MAP);back=_load(root,BACKLOG);parent=_load(root,PARENT)
    if parent.get("status")!="closed":raise P3LearningClosureError("parent P3-T1 closure must remain closed")
    status=c.get("status")
    if status not in {"active","closed"}:raise P3LearningClosureError("P3-T2 closure status must be active or closed")
    first=mp.get("first_tranche",{})
    if first.get("scheduled_volume_count")!=32 or first.get("queued_volume_count")!=165:raise P3LearningClosureError("P3-T2 closure partition drift")
    tasks={t.get("task_id"):t for t in back.get("tasks",[]) if isinstance(t,dict)}
    if set(tasks)!=set(EXPECTED):raise P3LearningClosureError("P3-T2 closure task inventory drift")
    for tid,t in tasks.items():
        if t.get("completion_checkbox") is not False or t.get("implementation_signed") is not False or t.get("verification_signed") is not False:raise P3LearningClosureError(f"{tid} may not self-complete or self-sign")
    for path in c.get("executable_surfaces",{}).values():
        if not isinstance(path,str) or not (root/path).is_file():raise P3LearningClosureError(f"closure executable surface missing: {path}")
    if c.get("deferred_scope",{}).get("queued_volume_count")!=165:raise P3LearningClosureError("P3-T2 deferred count drift")
    if c.get("handoff",{}).get("expected_volume_count")!=165:raise P3LearningClosureError("P3-T3 handoff drift")
    summary=back.get("summary",{})
    if mp.get("progress")!=summary:raise P3LearningClosureError("P3-T2 map/backlog progress drift")
    if status=="active":
        if any(tasks[x].get("status")!="landed_unpromoted" for x in set(EXPECTED)-{"P3T2-LIFECYCLE-01"}):raise P3LearningClosureError("previous T2 frontier regressed")
        if tasks["P3T2-LIFECYCLE-01"].get("status") not in {"in_progress","landed_unpromoted"}:raise P3LearningClosureError("lifecycle extension state drift")
        return {"status":"active","task_count":6,"scheduled_volume_count":32,"queued_volume_count":165}
    h=c.get("evidence_head")
    if not isinstance(h,str) or len(h)!=40:raise P3LearningClosureError("closed P3-T2 requires evidence_head")
    head=f"git-head:{h}";aggregate=f"workflow:P3 Learning Multimodal Acceptance@{h}:success"
    for tid,t in tasks.items():
        if t.get("status")!="landed_unpromoted":raise P3LearningClosureError(f"{tid} must be landed_unpromoted")
        refs=set(map(str,t.get("evidence_refs",[])))
        if head not in refs or aggregate not in refs:raise P3LearningClosureError(f"{tid} missing exact-head aggregate evidence")
        if tid=="P3T2-LIFECYCLE-01" and f"workflow:P3 Model Lifecycle@{h}:success" not in refs:raise P3LearningClosureError("lifecycle focused evidence missing")
    refs=set(map(str,c.get("evidence_refs",[])))
    for needed in {head,aggregate,f"workflow:P3 Model Lifecycle@{h}:success"}:
        if needed not in refs:raise P3LearningClosureError(f"closure missing exact-head evidence: {needed}")
    if summary.get("landed_unpromoted_count")!=6 or summary.get("in_progress_count")!=0:raise P3LearningClosureError("P3-T2 closed summary drift")
    return {"status":"closed","task_count":6,"scheduled_volume_count":32,"queued_volume_count":165,"evidence_head":h}
def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--json",action="store_true");a=p.parse_args(argv)
    try:r=validate(ROOT)
    except P3LearningClosureError as exc:print(f"P3 learning closure: FAIL: {exc}",file=sys.stderr);return 1
    print(json.dumps(r,indent=2,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
