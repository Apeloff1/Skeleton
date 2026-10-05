#!/usr/bin/env python3
"""Validate the VOL-231..VOL-240 deployment/operations gap-fill candidate."""
from __future__ import annotations
import argparse,json,re,subprocess,sys
from pathlib import Path
from typing import Any,Sequence
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_deployment_operations_gapfill_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=tuple(f"VOL-{value}" for value in range(231,241))
class DeploymentOperationsCandidateError(RuntimeError): pass
def _load(root:Path,path:Path)->dict[str,Any]:
    try: value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise DeploymentOperationsCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict): raise DeploymentOperationsCandidateError(f"{path} must contain object")
    return value
def _git(root:Path,*args:str)->str:
    result=subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,check=False)
    if result.returncode!=0: raise DeploymentOperationsCandidateError("git identity unavailable")
    return result.stdout.strip()
def validate(root:Path=ROOT,*,head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve(); candidate=_load(root,CANDIDATE); master=_load(root,MASTER)
    frontier=_load(root,FRONTIER); tree=_load(root,TREE)
    if candidate.get("schema_version")!="skeleton.ai.deployment_operations_gapfill_candidate.v1": raise DeploymentOperationsCandidateError("schema drift")
    if candidate.get("status")!="implementation_candidate": raise DeploymentOperationsCandidateError("status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED: raise DeploymentOperationsCandidateError("volume identity drift")
    if candidate.get("source_queue_state")!="queued_unmodified": raise DeploymentOperationsCandidateError("scheduling authority drift")
    if any(value is not False for value in candidate.get("promotion_state",{}).values()): raise DeploymentOperationsCandidateError("candidate self-promoted")
    tranche=frontier.get("next_tranche",{}); queued=set(tranche.get("queued_volume_refs",())); scheduled=set(tranche.get("scheduled_volume_refs",()))
    if set(EXPECTED)&scheduled: raise DeploymentOperationsCandidateError("volumes escaped into scheduled frontier")
    if not set(EXPECTED).issubset(queued): raise DeploymentOperationsCandidateError("volumes must remain queued")
    assurance=candidate.get("assurance_implementation"); shared=candidate.get("shared_implementation")
    for path in (assurance,shared):
        if not isinstance(path,str) or not (root/path).is_file(): raise DeploymentOperationsCandidateError(f"implementation missing: {path}")
    tests=candidate.get("primary_test_by_volume",{})
    if set(tests)!=set(EXPECTED): raise DeploymentOperationsCandidateError("test registry drift")
    volumes=master.get("volumes")
    if not isinstance(volumes,list): raise DeploymentOperationsCandidateError("masterplan volume registry missing")
    by_key={item.get("key"):item for item in volumes if isinstance(item,dict)}
    for key in EXPECTED:
        volume=by_key.get(key)
        if not isinstance(volume,dict): raise DeploymentOperationsCandidateError(f"missing {key}")
        if volume.get("implementation_status")!="implemented": raise DeploymentOperationsCandidateError(f"{key} must be implemented")
        if volume.get("completion_checkbox") is not False: raise DeploymentOperationsCandidateError(f"{key} completion self-promoted")
        if assurance not in set(volume.get("implementation_paths",())): raise DeploymentOperationsCandidateError(f"{key} missing assurance")
        if tests[key] not in set(volume.get("tests",())): raise DeploymentOperationsCandidateError(f"{key} missing regression")
        if any(str(item).startswith("planned:") for item in volume.get("tests",())): raise DeploymentOperationsCandidateError(f"{key} retains planned test")
        if not (root/tests[key]).is_file(): raise DeploymentOperationsCandidateError(f"{key} regression missing")
        gaps=volume.get("gaps")
        if not isinstance(gaps,list) or not any("independent exact-head" in str(item) for item in gaps): raise DeploymentOperationsCandidateError(f"{key} missing verification gap")
    mappings=tree.get("mappings")
    if not isinstance(mappings,list): raise DeploymentOperationsCandidateError("mapping registry missing")
    by_id={item.get("id"):item for item in mappings if isinstance(item,dict)}
    for volume_ref,mapping_id in candidate.get("mapping_requirements",{}).items():
        mapping=by_id.get(mapping_id)
        if not isinstance(mapping,dict): raise DeploymentOperationsCandidateError(f"missing mapping {mapping_id}")
        if volume_ref not in set(mapping.get("volume_refs",())): raise DeploymentOperationsCandidateError(f"{mapping_id} does not own {volume_ref}")
    actual=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual) is None: raise DeploymentOperationsCandidateError("checkout HEAD malformed")
    if head is not None and (re.fullmatch(r"[0-9a-f]{40}",head) is None or head!=actual): raise DeploymentOperationsCandidateError("reported head mismatch")
    return {"status":"valid","candidate_id":candidate["candidate_id"],"volume_refs":list(EXPECTED),"volume_count":10,"queued_frontier_preserved":True,"actual_head":actual,"reported_head":head,"completion_checkbox":False,"production_authority":False}
def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--head"); parser.add_argument("--json",action="store_true"); args=parser.parse_args(argv)
    try: result=validate(ROOT,head=args.head)
    except DeploymentOperationsCandidateError as exc: print(f"deployment operations gap-fill candidate: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else "deployment operations gap-fill candidate: OK"); return 0
if __name__=="__main__": raise SystemExit(main())
