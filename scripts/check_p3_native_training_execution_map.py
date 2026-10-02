#!/usr/bin/env python3
"""Fail-closed validation for the P3-T2 native-training frontier."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAP = Path("machine/ai_p3_native_training_execution_map.json")
BACKLOG = Path("machine/ai_p3_native_training_task_backlog.json")
PLAN = Path("machine/ai_p3_native_training_tranche.json")
PARENT = Path("machine/ai_p3_engineering_execution_map.json")
CLOSURE = Path("machine/ai_p3_engineering_closure.json")
MASTER = Path("machine/ai_master_plan.json")

class ValidationError(RuntimeError):
    pass

def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {rel}") from exc
    if not isinstance(value,dict):
        raise ValidationError(f"{rel} must contain an object")
    return value

def validate(root: Path = ROOT) -> dict[str, Any]:
    p=_load(root,MAP); b=_load(root,BACKLOG); plan=_load(root,PLAN)
    parent=_load(root,PARENT); closure=_load(root,CLOSURE); master=_load(root,MASTER)
    if closure.get("status")!="closed":
        raise ValidationError("P3-T1 closure must be closed")
    source=parent.get("first_tranche",{}).get("queued_volume_refs")
    if not isinstance(source,list) or len(source)!=197 or len(set(source))!=197:
        raise ValidationError("parent P3-T1 queue must contain 197 unique refs")
    declared=p.get("source_scope",{}).get("volume_refs")
    if declared!=source:
        raise ValidationError("P3-T2 source must equal exact P3-T1 queue")
    scheduled=p.get("first_tranche",{}).get("scheduled_volume_refs")
    queued=p.get("first_tranche",{}).get("queued_volume_refs")
    if not isinstance(scheduled,list) or not isinstance(queued,list):
        raise ValidationError("scheduled/queued partitions must be lists")
    if len(scheduled)!=24 or len(queued)!=173:
        raise ValidationError("P3-T2 partition must be 24 scheduled / 173 queued")
    if set(scheduled)&set(queued) or set(scheduled)|set(queued)!=set(source):
        raise ValidationError("P3-T2 partition does not exactly preserve source")
    if plan.get("selection",{}).get("selected_volume_refs")!=scheduled:
        raise ValidationError("tranche selection drift")

    master_by={v.get("key"):v for v in master.get("volumes",[]) if isinstance(v,dict)}
    tasks=b.get("tasks")
    if not isinstance(tasks,list) or len(tasks)!=5:
        raise ValidationError("P3-T2 must have five task owners")
    owned=[]
    ids={t.get("task_id") for t in tasks if isinstance(t,dict)}
    if len(ids)!=5 or None in ids:
        raise ValidationError("P3-T2 task ids must be unique")
    for task in tasks:
        if task.get("status") not in {"blocked","ready","in_progress","landed_unpromoted"}:
            raise ValidationError(f"unsupported task status: {task.get('task_id')}")
        for dep in task.get("depends_on",[]):
            if dep not in ids or dep==task.get("task_id"):
                raise ValidationError(f"invalid dependency for {task.get('task_id')}")
        refs=task.get("primary_volume_refs")
        obs=task.get("masterplan_obligations")
        if not isinstance(refs,list) or not isinstance(obs,list) or len(refs)!=len(obs):
            raise ValidationError(f"ownership/obligation mismatch for {task.get('task_id')}")
        owned.extend(refs)
        by_ref={o.get("volume_ref"):o for o in obs if isinstance(o,dict)}
        for ref in refs:
            if ref not in scheduled or ref not in master_by or ref not in by_ref:
                raise ValidationError(f"invalid owned volume {ref}")
            volume=master_by[ref]; ob=by_ref[ref]
            fields=("title","depth_pass","accountability_id","implementation_status","completion_checkbox","signing_required","requirements","capabilities","contracts","risks","gaps","implementation_paths","tests","evaluations")
            for field in fields:
                expected=volume.get(field,[] if field in {"requirements","capabilities","contracts","risks","gaps","implementation_paths","tests","evaluations"} else None)
                if ob.get(field)!=expected:
                    raise ValidationError(f"{task.get('task_id')} obligation drift {ref}.{field}")
        if task.get("completion_checkbox") is not False or task.get("implementation_signed") is not False or task.get("verification_signed") is not False:
            raise ValidationError(f"{task.get('task_id')} may not self-promote")
        if task.get("status")=="landed_unpromoted" and len(task.get("evidence_refs",[]))<6:
            raise ValidationError(f"{task.get('task_id')} landed state lacks exact-head evidence")
    if len(owned)!=24 or set(owned)!=set(scheduled) or len(set(owned))!=24:
        raise ValidationError("scheduled volumes require exactly one owner")

    return {
        "status":"valid","source_volume_count":197,"scheduled_volume_count":24,
        "queued_volume_count":173,"task_count":5,"owned_volume_count":24
    }

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--json",action="store_true"); args=parser.parse_args()
    try: result=validate(ROOT)
    except ValidationError as exc:
        print(f"P3 native training authority: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,sort_keys=True) if args.json else "P3 native training authority: OK (24 scheduled / 173 queued)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
