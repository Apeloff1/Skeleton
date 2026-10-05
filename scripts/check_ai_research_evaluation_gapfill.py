#!/usr/bin/env python3
"""Validate the deferred VOL-210..220 research/evaluation implementation candidate."""
from __future__ import annotations
import argparse,json,re,subprocess,sys
from pathlib import Path
from typing import Any,Sequence

ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_research_evaluation_gapfill_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=tuple(f"VOL-{value:03d}" for value in range(210,221))
RESEARCH={"VOL-210":"AIFT-RESEARCH-AGENT-TEAM","VOL-211":"AIFT-RESEARCH-LITERATURE-WATCH","VOL-212":"AIFT-RESEARCH-CITATION-GRAPH"}

class ResearchEvaluationCandidateError(RuntimeError): pass

def _load(root:Path,path:Path)->dict[str,Any]:
    try: value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ResearchEvaluationCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict): raise ResearchEvaluationCandidateError(f"{path} must contain an object")
    return value

def _git(root:Path,*args:str)->str:
    p=subprocess.run(["git","-C",str(root),*args],capture_output=True,text=True,check=False)
    if p.returncode!=0: raise ResearchEvaluationCandidateError("git identity unavailable")
    return p.stdout.strip()

def validate(root:Path=ROOT,*,head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    candidate=_load(root,CANDIDATE); master=_load(root,MASTER); frontier=_load(root,FRONTIER); tree=_load(root,TREE)
    if candidate.get("schema_version")!="skeleton.ai.research_evaluation_gapfill_candidate.v1": raise ResearchEvaluationCandidateError("candidate schema drift")
    if candidate.get("status")!="implementation_candidate": raise ResearchEvaluationCandidateError("candidate status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED: raise ResearchEvaluationCandidateError("candidate volume identity drift")
    if candidate.get("source_queue_state")!="queued_unmodified": raise ResearchEvaluationCandidateError("candidate may not claim scheduling authority")

    promotion=candidate.get("promotion_state",{})
    for key in ("completion_checkbox","implementation_signed","verification_signed","may_self_close","production_authority"):
        if promotion.get(key) is not False: raise ResearchEvaluationCandidateError(f"candidate illegally promoted {key}")
    evidence=candidate.get("evidence_policy",{})
    for key in ("exact_head_ci_required","independent_closure_required","queued_frontier_must_remain_unchanged","canonical_ai_mirror_parity_required","single_revision_review_required","independent_verifier_required","completion_may_not_be_self_granted"):
        if evidence.get(key) is not True: raise ResearchEvaluationCandidateError(f"missing evidence policy: {key}")

    tranche=frontier.get("next_tranche",{})
    scheduled=set(tranche.get("scheduled_volume_refs",())); queued=set(tranche.get("queued_volume_refs",()))
    if set(EXPECTED)&scheduled: raise ResearchEvaluationCandidateError("research/evaluation volumes escaped into scheduled frontier")
    if not set(EXPECTED).issubset(queued): raise ResearchEvaluationCandidateError("research/evaluation volumes must remain explicitly queued")

    modules=candidate.get("primary_implementation_by_volume",{}); tests=candidate.get("primary_test_by_volume",{})
    if set(modules)!=set(EXPECTED) or set(tests)!=set(EXPECTED): raise ResearchEvaluationCandidateError("per-volume registry drift")
    shared_module=candidate.get("shared_integration_module"); shared_test=candidate.get("shared_integration_test")
    if shared_module!="skeleton/eval/research_evaluation_review.py" or shared_test!="skeleton/testing/test_research_evaluation_review.py": raise ResearchEvaluationCandidateError("shared review declaration drift")
    if not (root/shared_module).is_file() or not (root/shared_test).is_file(): raise ResearchEvaluationCandidateError("shared review evidence missing")

    volumes=master.get("volumes")
    if not isinstance(volumes,list): raise ResearchEvaluationCandidateError("masterplan volume registry missing")
    by={v.get("key"):v for v in volumes if isinstance(v,dict)}
    for key in EXPECTED:
        v=by.get(key)
        if not isinstance(v,dict): raise ResearchEvaluationCandidateError(f"missing {key}")
        if v.get("implementation_status")!="implemented": raise ResearchEvaluationCandidateError(f"{key} must be implemented but not verified")
        if v.get("completion_checkbox") is not False: raise ResearchEvaluationCandidateError(f"{key} self-promoted completion")
        if modules[key] not in v.get("implementation_paths",()) or shared_module not in v.get("implementation_paths",()): raise ResearchEvaluationCandidateError(f"{key} implementation binding drift")
        if tests[key] not in v.get("tests",()) or shared_test not in v.get("tests",()): raise ResearchEvaluationCandidateError(f"{key} test binding drift")
        if any(str(x).startswith("planned:") for x in v.get("tests",())): raise ResearchEvaluationCandidateError(f"{key} retains planned test placeholder")
        if not (root/modules[key]).is_file() or not (root/tests[key]).is_file(): raise ResearchEvaluationCandidateError(f"{key} implementation/test file missing")
        if not v.get("gaps"): raise ResearchEvaluationCandidateError(f"{key} must retain independent verification gap")

    for path in candidate.get("cross_plane_tests",()):
        if not (root/path).is_file(): raise ResearchEvaluationCandidateError(f"cross-plane test missing: {path}")

    pairs=candidate.get("mirror_pairs")
    if not isinstance(pairs,list) or len(pairs)!=12: raise ResearchEvaluationCandidateError("mirror pair registry drift")
    for pair in pairs:
        if not isinstance(pair,list) or len(pair)!=2: raise ResearchEvaluationCandidateError("invalid mirror pair")
        left,right=root/pair[0],root/pair[1]
        if not left.is_file() or not right.is_file(): raise ResearchEvaluationCandidateError(f"mirror file missing: {pair}")
        if left.read_bytes()!=right.read_bytes(): raise ResearchEvaluationCandidateError(f"mirror parity drift: {pair[0]}")

    mappings=tree.get("mappings")
    if not isinstance(mappings,list): raise ResearchEvaluationCandidateError("AI file-tree mappings missing")
    by_id={m.get("id"):m for m in mappings if isinstance(m,dict)}
    for key,mapping_id in RESEARCH.items():
        m=by_id.get(mapping_id)
        if not isinstance(m,dict) or key not in set(m.get("volume_refs",())): raise ResearchEvaluationCandidateError(f"{mapping_id} volume coverage drift")
        actual=_git(root,"rev-parse",f"HEAD:{m['source']}")
        if m.get("source_git_object_sha")!=actual: raise ResearchEvaluationCandidateError(f"{mapping_id} source identity drift")
    eval_map=by_id.get("AIFT-EVALUATION"); art_map=by_id.get("AIFT-ARTIFACTS")
    if not isinstance(eval_map,dict) or not set(EXPECTED[4:]).issubset(set(eval_map.get("volume_refs",()))): raise ResearchEvaluationCandidateError("evaluation mapping coverage drift")
    if not isinstance(art_map,dict) or "VOL-213" not in set(art_map.get("volume_refs",())): raise ResearchEvaluationCandidateError("artifact mapping coverage drift")
    if eval_map.get("source_git_object_sha")!=_git(root,"rev-parse","HEAD:skeleton/eval"): raise ResearchEvaluationCandidateError("evaluation source tree identity drift")
    if art_map.get("source_git_object_sha")!=_git(root,"rev-parse","HEAD:skeleton/artifacts"): raise ResearchEvaluationCandidateError("artifact source tree identity drift")

    actual_head=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual_head) is None: raise ResearchEvaluationCandidateError("checkout HEAD malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None: raise ResearchEvaluationCandidateError("reported exact head malformed")
        if head!=actual_head: raise ResearchEvaluationCandidateError("reported exact head does not match checkout")

    return {"status":"valid","candidate_id":candidate["candidate_id"],"volume_count":11,"mirror_pair_count":12,"queued_frontier_preserved":True,"actual_head":actual_head,"reported_head":head,"completion_checkbox":False,"production_authority":False}

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--head"); p.add_argument("--json",action="store_true"); args=p.parse_args(argv)
    try: result=validate(ROOT,head=args.head)
    except ResearchEvaluationCandidateError as exc:
        print(f"research evaluation gap-fill candidate: FAIL: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else "research evaluation gap-fill candidate: OK"); return 0

if __name__=="__main__": raise SystemExit(main())
