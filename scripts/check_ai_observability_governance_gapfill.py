#!/usr/bin/env python3
"""Validate the deferred observability-governance masterplan gap-fill candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_observability_governance_gapfill_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=(
    "VOL-180","VOL-181","VOL-182","VOL-183",
    "VOL-184","VOL-185","VOL-186","VOL-187",
)


class ObservabilityGovernanceCandidateError(RuntimeError):
    pass


def _load(root:Path,path:Path)->dict[str,Any]:
    try:
        value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise ObservabilityGovernanceCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict):
        raise ObservabilityGovernanceCandidateError(f"{path} must contain an object")
    return value


def _git(root:Path,*args:str)->str:
    result=subprocess.run(
        ["git","-C",str(root),*args],
        capture_output=True,text=True,check=False,
    )
    if result.returncode!=0:
        raise ObservabilityGovernanceCandidateError("git identity unavailable")
    return result.stdout.strip()


def validate(root:Path=ROOT, *, head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    candidate=_load(root,CANDIDATE)
    master=_load(root,MASTER)
    frontier=_load(root,FRONTIER)
    tree=_load(root,TREE)

    if candidate.get("schema_version")!="skeleton.ai.observability_governance_gapfill_candidate.v1":
        raise ObservabilityGovernanceCandidateError("candidate schema drift")
    if candidate.get("status")!="implementation_candidate":
        raise ObservabilityGovernanceCandidateError("candidate status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED:
        raise ObservabilityGovernanceCandidateError("candidate volume identity drift")
    if candidate.get("source_queue_state")!="queued_unmodified":
        raise ObservabilityGovernanceCandidateError("candidate may not claim scheduling authority")

    promotion=candidate.get("promotion_state",{})
    for key in (
        "completion_checkbox","implementation_signed","verification_signed",
        "may_self_close","production_authority",
    ):
        if promotion.get(key) is not False:
            raise ObservabilityGovernanceCandidateError(f"candidate illegally promoted {key}")

    evidence=candidate.get("evidence_policy",{})
    for key in (
        "exact_head_ci_required","independent_closure_required",
        "queued_frontier_must_remain_unchanged",
        "canonical_ai_mirror_parity_required",
        "completion_may_not_be_self_granted",
    ):
        if evidence.get(key) is not True:
            raise ObservabilityGovernanceCandidateError(f"missing evidence policy: {key}")

    tranche=frontier.get("next_tranche",{})
    scheduled=set(tranche.get("scheduled_volume_refs",()))
    queued=set(tranche.get("queued_volume_refs",()))
    if set(EXPECTED)&scheduled:
        raise ObservabilityGovernanceCandidateError(
            "deferred observability volumes escaped into scheduled frontier"
        )
    if not set(EXPECTED).issubset(queued):
        raise ObservabilityGovernanceCandidateError(
            "deferred observability volumes must remain explicitly queued"
        )

    modules=candidate.get("primary_implementation_by_volume",{})
    tests=candidate.get("primary_test_by_volume",{})
    if set(modules)!=set(EXPECTED) or set(tests)!=set(EXPECTED):
        raise ObservabilityGovernanceCandidateError("per-volume module/test registry drift")

    volumes=master.get("volumes")
    if not isinstance(volumes,list):
        raise ObservabilityGovernanceCandidateError("masterplan volume registry missing")
    by_key={value.get("key"):value for value in volumes if isinstance(value,dict)}
    for key in EXPECTED:
        volume=by_key.get(key)
        if not isinstance(volume,dict):
            raise ObservabilityGovernanceCandidateError(f"masterplan volume missing: {key}")
        if volume.get("implementation_status")!="implemented":
            raise ObservabilityGovernanceCandidateError(f"{key} must be implemented but not verified")
        if volume.get("completion_checkbox") is not False:
            raise ObservabilityGovernanceCandidateError(f"{key} completion checkbox self-promoted")
        module=modules[key]
        test=tests[key]
        paths=set(volume.get("implementation_paths",()))
        if module not in paths:
            raise ObservabilityGovernanceCandidateError(f"{key} missing canonical implementation path")
        mirror=module.replace("skeleton/observability/","skeleton/ai/runtime/observability/",1)
        if mirror not in paths:
            raise ObservabilityGovernanceCandidateError(f"{key} missing AI runtime mirror path")
        if test not in volume.get("tests",()):
            raise ObservabilityGovernanceCandidateError(f"{key} missing executable primary test")
        if any(str(item).startswith("planned:") for item in volume.get("tests",())):
            raise ObservabilityGovernanceCandidateError(f"{key} retains planned test placeholder")
        if not (root/module).is_file() or not (root/mirror).is_file() or not (root/test).is_file():
            raise ObservabilityGovernanceCandidateError(f"{key} implementation/test file missing")
        gaps=volume.get("gaps")
        if not isinstance(gaps,list) or not gaps:
            raise ObservabilityGovernanceCandidateError(
                f"{key} must retain independent exact-head verification gap"
            )

    pairs=candidate.get("mirror_pairs")
    if not isinstance(pairs,list) or len(pairs)!=len(EXPECTED):
        raise ObservabilityGovernanceCandidateError("mirror pair registry drift")
    for pair in pairs:
        if not isinstance(pair,list) or len(pair)!=2:
            raise ObservabilityGovernanceCandidateError("invalid mirror pair declaration")
        left,right=(root/pair[0],root/pair[1])
        if not left.is_file() or not right.is_file():
            raise ObservabilityGovernanceCandidateError(f"mirror file missing: {pair}")
        if left.read_bytes()!=right.read_bytes():
            raise ObservabilityGovernanceCandidateError(f"mirror parity drift: {pair[0]}")

    mappings=tree.get("mappings")
    if not isinstance(mappings,list):
        raise ObservabilityGovernanceCandidateError("AI file-tree mapping registry missing")
    by_id={item.get("id"):item for item in mappings if isinstance(item,dict)}
    mapping=by_id.get("AIFT-OBSERVABILITY")
    if not isinstance(mapping,dict):
        raise ObservabilityGovernanceCandidateError("AIFT-OBSERVABILITY mapping missing")
    if not set(EXPECTED).issubset(set(mapping.get("volume_refs",()))):
        raise ObservabilityGovernanceCandidateError(
            "observability mapping volume coverage drift"
        )
    source_tree=_git(root,"rev-parse","HEAD:skeleton/observability")
    if mapping.get("source_git_object_sha")!=source_tree:
        raise ObservabilityGovernanceCandidateError(
            "AIFT-OBSERVABILITY source tree identity drift"
        )

    actual_head=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual_head) is None:
        raise ObservabilityGovernanceCandidateError("checkout HEAD identity malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None:
            raise ObservabilityGovernanceCandidateError("reported exact head malformed")
        if head!=actual_head:
            raise ObservabilityGovernanceCandidateError(
                "reported exact head does not match checkout"
            )

    return {
        "status":"valid",
        "candidate_id":candidate["candidate_id"],
        "volume_refs":list(EXPECTED),
        "volume_count":len(EXPECTED),
        "mirror_pair_count":len(pairs),
        "observability_tree_sha":source_tree,
        "actual_head":actual_head,
        "reported_head":head,
        "queued_frontier_preserved":True,
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
    except ObservabilityGovernanceCandidateError as exc:
        print(f"observability governance gap-fill candidate: FAIL: {exc}",file=sys.stderr)
        return 1
    print(
        json.dumps(result,indent=2,sort_keys=True)
        if args.json
        else "observability governance gap-fill candidate: OK"
    )
    return 0


if __name__=="__main__":
    raise SystemExit(main())
