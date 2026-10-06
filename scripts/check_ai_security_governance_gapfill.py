#!/usr/bin/env python3
"""Validate the deferred security/governance masterplan gap-fill candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_security_governance_gapfill_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
P2_MAP=Path("machine/ai_p2_execution_map.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=(
    "VOL-166","VOL-173","VOL-174","VOL-176","VOL-177","VOL-178",
)
P2_SCHEDULED=frozenset({"VOL-167","VOL-169","VOL-172","VOL-175"})
SECURITY_VOLUMES=frozenset(EXPECTED[:-1])
SUPPLY_VOLUMES=frozenset({"VOL-178"})


class SecurityGovernanceCandidateError(RuntimeError):
    pass


def _load(root:Path,path:Path)->dict[str,Any]:
    try:
        value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise SecurityGovernanceCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict):
        raise SecurityGovernanceCandidateError(f"{path} must contain an object")
    return value


def _git(root:Path,*args:str)->str:
    result=subprocess.run(
        ["git","-C",str(root),*args],
        capture_output=True,text=True,check=False,
    )
    if result.returncode!=0:
        raise SecurityGovernanceCandidateError("git identity unavailable")
    return result.stdout.strip()


def validate(root:Path=ROOT, *, head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    candidate=_load(root,CANDIDATE)
    master=_load(root,MASTER)
    frontier=_load(root,FRONTIER)
    p2_map=_load(root,P2_MAP)
    tree=_load(root,TREE)

    if candidate.get("schema_version")!="skeleton.ai.security_governance_gapfill_candidate.v1":
        raise SecurityGovernanceCandidateError("candidate schema drift")
    if candidate.get("status")!="implementation_candidate":
        raise SecurityGovernanceCandidateError("candidate status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED:
        raise SecurityGovernanceCandidateError("candidate volume identity drift")
    if candidate.get("source_queue_state")!="p3_deferred_with_p2_scheduled_predecessors":
        raise SecurityGovernanceCandidateError("candidate lifecycle classification drift")
    if set(candidate.get("p2_scheduled_volume_refs",()))!=P2_SCHEDULED:
        raise SecurityGovernanceCandidateError("P2 scheduled predecessor registry drift")

    promotion=candidate.get("promotion_state",{})
    for key in (
        "completion_checkbox","implementation_signed","verification_signed",
        "may_self_close","production_authority",
    ):
        if promotion.get(key) is not False:
            raise SecurityGovernanceCandidateError(f"candidate illegally promoted {key}")

    evidence=candidate.get("evidence_policy",{})
    for key in (
        "exact_head_ci_required","independent_closure_required",
        "queued_frontier_must_remain_unchanged",
        "canonical_ai_mirror_parity_required",
        "completion_may_not_be_self_granted",
    ):
        if evidence.get(key) is not True:
            raise SecurityGovernanceCandidateError(f"missing evidence policy: {key}")

    tranche=frontier.get("next_tranche",{})
    scheduled=set(tranche.get("scheduled_volume_refs",()))
    queued=set(tranche.get("queued_volume_refs",()))
    if set(EXPECTED)&scheduled:
        raise SecurityGovernanceCandidateError("deferred gap-fill volumes escaped into scheduled frontier")
    if not set(EXPECTED).issubset(queued):
        raise SecurityGovernanceCandidateError("deferred gap-fill volumes must remain explicitly queued")
    p2_scheduled=set(p2_map.get("first_tranche",{}).get("scheduled_volume_refs",()))
    if not P2_SCHEDULED.issubset(p2_scheduled):
        raise SecurityGovernanceCandidateError("historical P2 scheduling evidence drift")

    modules=candidate.get("primary_implementation_by_volume",{})
    tests=candidate.get("primary_test_by_volume",{})
    if set(modules)!=set(EXPECTED) or set(tests)!=set(EXPECTED):
        raise SecurityGovernanceCandidateError("per-volume module/test registry drift")

    volumes=master.get("volumes")
    if not isinstance(volumes,list):
        raise SecurityGovernanceCandidateError("masterplan volume registry missing")
    by_key={value.get("key"):value for value in volumes if isinstance(value,dict)}
    for key in EXPECTED:
        volume=by_key.get(key)
        if not isinstance(volume,dict):
            raise SecurityGovernanceCandidateError(f"masterplan volume missing: {key}")
        if volume.get("implementation_status")!="implemented":
            raise SecurityGovernanceCandidateError(f"{key} must be implemented but not verified")
        if volume.get("completion_checkbox") is not False:
            raise SecurityGovernanceCandidateError(f"{key} completion checkbox self-promoted")
        module=modules[key]
        test=tests[key]
        if module not in volume.get("implementation_paths",()):
            raise SecurityGovernanceCandidateError(f"{key} missing implementation path")
        if test not in volume.get("tests",()):
            raise SecurityGovernanceCandidateError(f"{key} missing executable primary test")
        if any(str(item).startswith("planned:") for item in volume.get("tests",())):
            raise SecurityGovernanceCandidateError(f"{key} retains planned test placeholder")
        if not (root/module).is_file() or not (root/test).is_file():
            raise SecurityGovernanceCandidateError(f"{key} implementation/test file missing")
        gaps=volume.get("gaps")
        if not isinstance(gaps,list) or not gaps:
            raise SecurityGovernanceCandidateError(f"{key} must retain independent verification gap")

    cross=candidate.get("cross_plane_tests")
    if not isinstance(cross,list) or len(cross)!=len(set(cross)) or not cross:
        raise SecurityGovernanceCandidateError("cross-plane test registry drift")
    for test in cross:
        if not (root/test).is_file():
            raise SecurityGovernanceCandidateError(f"cross-plane test missing: {test}")

    pairs=candidate.get("mirror_pairs")
    if not isinstance(pairs,list) or not pairs:
        raise SecurityGovernanceCandidateError("mirror pair registry missing")
    for pair in pairs:
        if not isinstance(pair,list) or len(pair)!=2:
            raise SecurityGovernanceCandidateError("invalid mirror pair declaration")
        left,right=(root/pair[0],root/pair[1])
        if not left.is_file() or not right.is_file():
            raise SecurityGovernanceCandidateError(f"mirror file missing: {pair}")
        if left.read_bytes()!=right.read_bytes():
            raise SecurityGovernanceCandidateError(f"mirror parity drift: {pair[0]}")

    mappings=tree.get("mappings")
    if not isinstance(mappings,list):
        raise SecurityGovernanceCandidateError("AI file-tree mapping registry missing")
    by_id={item.get("id"):item for item in mappings if isinstance(item,dict)}
    security=by_id.get("AIFT-SECURITY")
    supply=by_id.get("AIFT-SUPPLY-CHAIN")
    if not isinstance(security,dict) or not isinstance(supply,dict):
        raise SecurityGovernanceCandidateError("required AI file-tree mappings missing")
    if not SECURITY_VOLUMES.issubset(set(security.get("volume_refs",()))):
        raise SecurityGovernanceCandidateError("security mapping volume coverage drift")
    if not SUPPLY_VOLUMES.issubset(set(supply.get("volume_refs",()))):
        raise SecurityGovernanceCandidateError("supply-chain mapping volume coverage drift")

    security_tree=_git(root,"rev-parse","HEAD:skeleton/security")
    supply_tree=_git(root,"rev-parse","HEAD:skeleton/supply_chain")
    if security.get("source_git_object_sha")!=security_tree:
        raise SecurityGovernanceCandidateError("AIFT-SECURITY source tree identity drift")
    if supply.get("source_git_object_sha")!=supply_tree:
        raise SecurityGovernanceCandidateError("AIFT-SUPPLY-CHAIN source tree identity drift")

    actual_head=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual_head) is None:
        raise SecurityGovernanceCandidateError("checkout HEAD identity malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None:
            raise SecurityGovernanceCandidateError("reported exact head malformed")
        if head!=actual_head:
            raise SecurityGovernanceCandidateError("reported exact head does not match checkout")

    return {
        "status":"valid",
        "candidate_id":candidate["candidate_id"],
        "volume_refs":list(EXPECTED),
        "volume_count":len(EXPECTED),
        "primary_test_count":len(EXPECTED),
        "cross_plane_test_count":len(cross),
        "mirror_pair_count":len(pairs),
        "security_tree_sha":security_tree,
        "supply_chain_tree_sha":supply_tree,
        "actual_head":actual_head,
        "reported_head":head,
        "queued_frontier_preserved":True,
        "p2_scheduled_predecessors":sorted(P2_SCHEDULED),
        "completion_checkbox":False,
        "production_authority":False,
    }


def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=validate(ROOT,head=args.head)
    except SecurityGovernanceCandidateError as exc:
        print(f"security governance gap-fill candidate: FAIL: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else "security governance gap-fill candidate: OK")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
