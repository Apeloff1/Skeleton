#!/usr/bin/env python3
"""Validate the October 2026 engineering-standards candidate for VOL-221..234."""
from __future__ import annotations
import argparse,json,re,subprocess,sys
from pathlib import Path
from typing import Any,Sequence

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_oct2026_engineering_standards_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=tuple(f"VOL-{n:03d}" for n in range(221,235))

class Oct2026StandardsCandidateError(RuntimeError): pass

def _load(root:Path,path:Path)->dict[str,Any]:
    try:value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise Oct2026StandardsCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict): raise Oct2026StandardsCandidateError(f"{path} must contain object")
    return value

def _git(root:Path,*args:str)->str:
    p=subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,check=False)
    if p.returncode!=0: raise Oct2026StandardsCandidateError("git identity unavailable")
    return p.stdout.strip()

def validate(root:Path=ROOT,*,head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    c=_load(root,CANDIDATE); master=_load(root,MASTER); frontier=_load(root,FRONTIER); tree=_load(root,TREE)
    if c.get("schema_version")!="skeleton.ai.oct2026_engineering_standards_candidate.v1": raise Oct2026StandardsCandidateError("candidate schema drift")
    if c.get("status")!="implementation_candidate": raise Oct2026StandardsCandidateError("candidate status drift")
    if tuple(c.get("volume_refs",()))!=EXPECTED: raise Oct2026StandardsCandidateError("candidate volume identity drift")
    if c.get("source_queue_state")!="queued_unmodified": raise Oct2026StandardsCandidateError("candidate may not claim scheduling authority")

    promotion=c.get("promotion_state",{})
    for key in ("completion_checkbox","implementation_signed","verification_signed","may_self_close","production_authority"):
        if promotion.get(key) is not False: raise Oct2026StandardsCandidateError(f"candidate illegally promoted {key}")
    policy=c.get("evidence_policy",{})
    for key in ("exact_head_ci_required","independent_closure_required","queued_frontier_must_remain_unchanged","fail_closed_authority_required","content_addressed_evidence_required","least_privilege_admin_required","capability_safe_failover_required","network_explicitness_required","completion_may_not_be_self_granted"):
        if policy.get(key) is not True: raise Oct2026StandardsCandidateError(f"missing evidence policy: {key}")

    tranche=frontier.get("next_tranche",{})
    queued=set(tranche.get("queued_volume_refs",())); scheduled=set(tranche.get("scheduled_volume_refs",()))
    if set(EXPECTED)&scheduled: raise Oct2026StandardsCandidateError("standards volumes escaped into scheduled frontier")
    if not set(EXPECTED).issubset(queued): raise Oct2026StandardsCandidateError("standards volumes must remain explicitly queued")

    modules=c.get("primary_implementation_by_volume",{}); tests=c.get("primary_test_by_volume",{})
    if set(modules)!=set(EXPECTED) or set(tests)!=set(EXPECTED): raise Oct2026StandardsCandidateError("per-volume registry drift")
    review_module=c.get("shared_review_module"); review_test=c.get("shared_review_test")
    if review_module!="skeleton/ai/governance/engineering_standards_review.py" or review_test!="skeleton/testing/test_engineering_standards_review.py": raise Oct2026StandardsCandidateError("shared review declaration drift")
    if not (root/review_module).is_file() or not (root/review_test).is_file(): raise Oct2026StandardsCandidateError("shared review missing")

    volumes=master.get("volumes")
    if not isinstance(volumes,list): raise Oct2026StandardsCandidateError("master volume registry missing")
    by={v.get("key"):v for v in volumes if isinstance(v,dict)}
    for key in EXPECTED:
        v=by.get(key)
        if not isinstance(v,dict): raise Oct2026StandardsCandidateError(f"missing {key}")
        if v.get("implementation_status")!="implemented": raise Oct2026StandardsCandidateError(f"{key} must be implemented but unverified")
        if v.get("completion_checkbox") is not False: raise Oct2026StandardsCandidateError(f"{key} self-promoted completion")
        if v.get("implementation_paths")!=[modules[key]]: raise Oct2026StandardsCandidateError(f"{key} implementation binding drift")
        if tests[key] not in v.get("tests",()) or review_test not in v.get("tests",()): raise Oct2026StandardsCandidateError(f"{key} test binding drift")
        if any(str(x).startswith("planned:") for x in v.get("tests",())): raise Oct2026StandardsCandidateError(f"{key} retains planned test placeholder")
        if not (root/modules[key]).is_file() or not (root/tests[key]).is_file(): raise Oct2026StandardsCandidateError(f"{key} implementation/test missing")
        if not v.get("gaps"): raise Oct2026StandardsCandidateError(f"{key} must retain independent verification gap")

    for path in c.get("cross_plane_tests",()):
        if not (root/path).is_file(): raise Oct2026StandardsCandidateError(f"cross-plane test missing: {path}")

    pairs=c.get("security_mirror_pairs")
    if not isinstance(pairs,list) or len(pairs)!=2: raise Oct2026StandardsCandidateError("security mirror registry drift")
    for pair in pairs:
        if not isinstance(pair,list) or len(pair)!=2: raise Oct2026StandardsCandidateError("invalid security mirror pair")
        left,right=root/pair[0],root/pair[1]
        if not left.is_file() or not right.is_file(): raise Oct2026StandardsCandidateError(f"security mirror missing: {pair}")
        if left.read_bytes()!=right.read_bytes(): raise Oct2026StandardsCandidateError(f"security mirror parity drift: {pair[0]}")

    mappings=tree.get("mappings",[]); native=tree.get("native_ai_owners",[])
    mapping_by={m.get("id"):m for m in mappings if isinstance(m,dict)}
    native_by={m.get("id"):m for m in native if isinstance(m,dict)}
    owners=c.get("owner_contract",{})
    for owner_id,refs in owners.items():
        owner=mapping_by.get(owner_id) or native_by.get(owner_id)
        if not isinstance(owner,dict): raise Oct2026StandardsCandidateError(f"owner missing: {owner_id}")
        if not set(refs).issubset(set(owner.get("volume_refs",()))): raise Oct2026StandardsCandidateError(f"owner volume coverage drift: {owner_id}")
    governance=native_by.get("AIFT-NATIVE-GOVERNANCE-ROOT")
    if not isinstance(governance,dict) or governance.get("path")!="skeleton/ai/governance" or governance.get("ownership_mode")!="canonical_native": raise Oct2026StandardsCandidateError("governance native owner drift")
    security=mapping_by.get("AIFT-SECURITY")
    if not isinstance(security,dict): raise Oct2026StandardsCandidateError("security mapping missing")
    if security.get("source_git_object_sha")!=_git(root,"rev-parse","HEAD:skeleton/security"): raise Oct2026StandardsCandidateError("security source tree identity drift")

    actual=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual) is None: raise Oct2026StandardsCandidateError("checkout HEAD malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None: raise Oct2026StandardsCandidateError("reported exact head malformed")
        if head!=actual: raise Oct2026StandardsCandidateError("reported exact head does not match checkout")
    return {"status":"valid","candidate_id":c["candidate_id"],"volume_count":14,"security_mirror_pair_count":2,"queued_frontier_preserved":True,"actual_head":actual,"reported_head":head,"completion_checkbox":False,"production_authority":False}

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--head"); p.add_argument("--json",action="store_true"); args=p.parse_args(argv)
    try:result=validate(ROOT,head=args.head)
    except Oct2026StandardsCandidateError as exc:
        print(f"oct2026 engineering standards candidate: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else "oct2026 engineering standards candidate: OK"); return 0

if __name__=="__main__": raise SystemExit(main())
