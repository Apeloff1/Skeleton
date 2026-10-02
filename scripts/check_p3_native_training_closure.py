#!/usr/bin/env python3
"""Validate the bounded P3-T2 native model-development closure."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
CLOSURE=Path("machine/ai_p3_native_training_closure.json")
MAP=Path("machine/ai_p3_native_training_execution_map.json")
BACKLOG=Path("machine/ai_p3_native_training_task_backlog.json")
PARENT=Path("machine/ai_p3_engineering_closure.json")

class ClosureError(RuntimeError):
    pass

def _load(root: Path, rel: Path) -> dict[str,Any]:
    try: value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ClosureError(f"cannot read {rel}") from exc
    if not isinstance(value,dict): raise ClosureError(f"{rel} must contain an object")
    return value

def validate(root: Path=ROOT) -> dict[str,Any]:
    closure=_load(root,CLOSURE); p=_load(root,MAP); backlog=_load(root,BACKLOG); parent=_load(root,PARENT)
    if parent.get("status")!="closed":
        raise ClosureError("P3-T1 parent closure must remain closed")
    if closure.get("status")!="closed":
        raise ClosureError("P3-T2 closure must be closed")
    frontier=closure.get("frontier",{})
    scheduled=p.get("first_tranche",{}).get("scheduled_volume_refs")
    queued=p.get("first_tranche",{}).get("queued_volume_refs")
    if frontier.get("scheduled_volume_refs")!=scheduled:
        raise ClosureError("closure scheduled frontier drift")
    if frontier.get("scheduled_volume_count")!=24 or len(scheduled or [])!=24:
        raise ClosureError("closure must bind 24 scheduled volumes")
    if frontier.get("queued_volume_count")!=173 or len(queued or [])!=173:
        raise ClosureError("closure must preserve 173 queued volumes")
    if closure.get("deferred_scope",{}).get("queued_volume_refs")!=queued:
        raise ClosureError("closure deferred scope drift")

    tasks=backlog.get("tasks",[])
    if len(tasks)!=5 or p.get("progress",{}).get("landed_unpromoted_count")!=5:
        raise ClosureError("all five P3-T2 owners must be evidence-landed")
    if frontier.get("task_ids")!=[task.get("task_id") for task in tasks]:
        raise ClosureError("closure task inventory drift")
    for task in tasks:
        if task.get("status")!="landed_unpromoted":
            raise ClosureError(f"{task.get('task_id')} is not landed_unpromoted")
        if task.get("completion_checkbox") is not False:
            raise ClosureError(f"{task.get('task_id')} self-completed")
        if task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
            raise ClosureError(f"{task.get('task_id')} self-signed")
        refs=task.get("evidence_refs",[])
        if len(refs)<9 or not any(str(ref).startswith("git-head:") for ref in refs):
            raise ClosureError(f"{task.get('task_id')} lacks executable evidence")

    surfaces=closure.get("executable_surfaces",{})
    for path in surfaces.values():
        if not isinstance(path,str) or not (root/path).is_file():
            raise ClosureError(f"closure executable surface missing: {path}")

    evidence=closure.get("closure_evidence",[])
    if not any(str(ref).startswith("workflow:P3 Native Model Acceptance@") and str(ref).endswith(":success") for ref in evidence):
        raise ClosureError("closure lacks successful aggregate acceptance evidence")

    return {
        "status":"closed","scheduled_volume_count":24,"queued_volume_count":173,
        "task_count":5,"provider_independent":True,
    }

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--json",action="store_true"); args=parser.parse_args()
    try: result=validate(ROOT)
    except ClosureError as exc:
        print(f"P3 native training closure: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,sort_keys=True) if args.json else "P3 native training closure: OK (24 landed / 173 queued)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
