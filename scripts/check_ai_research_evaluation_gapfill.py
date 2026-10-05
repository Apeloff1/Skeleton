#!/usr/bin/env python3
"""Validate the VOL-210..VOL-220 research/evaluation gap-fill candidate."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any,Sequence

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_research_evaluation_gapfill_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=tuple(f"VOL-{value}" for value in range(210,221))

class ResearchEvaluationCandidateError(RuntimeError):
    pass

def _load(root:Path,path:Path)->dict[str,Any]:
    try:
        value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise ResearchEvaluationCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict):
        raise ResearchEvaluationCandidateError(f"{path} must contain an object")
    return value

def _git(root:Path,*args:str)->str:
    result=subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,check=False)
    if result.returncode!=0:
        raise ResearchEvaluationCandidateError("git identity unavailable")
    return result.stdout.strip()

def validate(root:Path=ROOT,*,head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    candidate=_load(root,CANDIDATE)
    master=_load(root,MASTER)
    frontier=_load(root,FRONTIER)
    tree=_load(root,TREE)
    if candidate.get("schema_version")!="skeleton.ai.research_evaluation_gapfill_candidate.v1":
        raise ResearchEvaluationCandidateError("candidate schema drift")
    if candidate.get("status")!="implementation_candidate":
        raise ResearchEvaluationCandidateError("candidate status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED:
        raise ResearchEvaluationCandidateError("candidate volume identity drift")
    if candidate.get("source_queue_state")!="queued_unmodified":
        raise ResearchEvaluationCandidateError("candidate may not claim scheduling authority")
    for key,value in candidate.get("promotion_state",{}).items():
        if value is not False:
            raise ResearchEvaluationCandidateError(f"candidate illegally promoted {key}")
    policy=candidate.get("evidence_policy",{})
    for key in (
        "exact_head_ci_required","independent_closure_required",
        "queued_frontier_must_remain_unchanged",
        "completion_may_not_be_self_granted",
        "production_authority_must_remain_false",
    ):
        if policy.get(key) is not True:
            raise ResearchEvaluationCandidateError(f"missing evidence policy: {key}")
    tranche=frontier.get("next_tranche",{})
    queued=set(tranche.get("queued_volume_refs",()))
    scheduled=set(tranche.get("scheduled_volume_refs",()))
    if set(EXPECTED)&scheduled:
        raise ResearchEvaluationCandidateError("research/evaluation volumes escaped into scheduled frontier")
    if not set(EXPECTED).issubset(queued):
        raise ResearchEvaluationCandidateError("research/evaluation volumes must remain queued")
    shared=candidate.get("shared_implementation")
    assurance=candidate.get("assurance_implementation")
    if shared!="skeleton/ai/runtime/deferred/research_evaluation.py":
        raise ResearchEvaluationCandidateError("shared implementation identity drift")
    if assurance!="skeleton/ai/runtime/deferred/research_evaluation_assurance.py":
        raise ResearchEvaluationCandidateError("assurance implementation identity drift")
    for path in (shared,assurance):
        if not (root/path).is_file():
            raise ResearchEvaluationCandidateError(f"implementation missing: {path}")
    tests=candidate.get("primary_test_by_volume",{})
    if set(tests)!=set(EXPECTED):
        raise ResearchEvaluationCandidateError("per-volume test registry drift")
    volumes=master.get("volumes")
    if not isinstance(volumes,list):
        raise ResearchEvaluationCandidateError("masterplan volume registry missing")
    by_key={item.get("key"):item for item in volumes if isinstance(item,dict)}
    for key in EXPECTED:
        volume=by_key.get(key)
        if not isinstance(volume,dict):
            raise ResearchEvaluationCandidateError(f"masterplan volume missing: {key}")
        if volume.get("implementation_status")!="implemented":
            raise ResearchEvaluationCandidateError(f"{key} must be implemented but unsigned")
        if volume.get("completion_checkbox") is not False:
            raise ResearchEvaluationCandidateError(f"{key} completion checkbox self-promoted")
        paths=set(volume.get("implementation_paths",()))
        if shared not in paths or assurance not in paths:
            raise ResearchEvaluationCandidateError(f"{key} missing shared/assurance implementation")
        if tests[key] not in set(volume.get("tests",())):
            raise ResearchEvaluationCandidateError(f"{key} missing primary regression")
        if any(str(item).startswith("planned:") for item in volume.get("tests",())):
            raise ResearchEvaluationCandidateError(f"{key} retains planned test placeholder")
        if not (root/tests[key]).is_file():
            raise ResearchEvaluationCandidateError(f"{key} primary regression file missing")
        gaps=volume.get("gaps")
        if not isinstance(gaps,list) or not any("independent exact-head" in str(item) for item in gaps):
            raise ResearchEvaluationCandidateError(f"{key} must retain independent exact-head verification gap")
    mappings=tree.get("mappings")
    if not isinstance(mappings,list):
        raise ResearchEvaluationCandidateError("AI file-tree mapping registry missing")
    by_id={item.get("id"):item for item in mappings if isinstance(item,dict)}
    for volume_ref,mapping_id in candidate.get("mapping_requirements",{}).items():
        mapping=by_id.get(mapping_id)
        if not isinstance(mapping,dict):
            raise ResearchEvaluationCandidateError(f"required mapping missing: {mapping_id}")
        if volume_ref not in set(mapping.get("volume_refs",())):
            raise ResearchEvaluationCandidateError(f"{mapping_id} does not own {volume_ref}")
    actual_head=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual_head) is None:
        raise ResearchEvaluationCandidateError("checkout HEAD identity malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None or head!=actual_head:
            raise ResearchEvaluationCandidateError("reported exact head does not match checkout")
    return {
        "status":"valid","candidate_id":candidate["candidate_id"],
        "volume_refs":list(EXPECTED),"volume_count":len(EXPECTED),
        "queued_frontier_preserved":True,"actual_head":actual_head,
        "reported_head":head,"completion_checkbox":False,"production_authority":False,
    }

def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=validate(ROOT,head=args.head)
    except ResearchEvaluationCandidateError as exc:
        print(f"research evaluation gap-fill candidate: FAIL: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else "research evaluation gap-fill candidate: OK")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
