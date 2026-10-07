#!/usr/bin/env python3
"""Validate the deferred observability/economics masterplan gap-fill candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_observability_economics_gapfill_candidate.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=tuple(f"VOL-{value:03d}" for value in range(180,188))


class ObservabilityEconomicsCandidateError(RuntimeError):
    pass


def _load(root:Path,path:Path)->dict[str,Any]:
    try:
        value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise ObservabilityEconomicsCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict):
        raise ObservabilityEconomicsCandidateError(f"{path} must contain an object")
    return value


def _git(root:Path,*args:str)->str:
    result=subprocess.run(
        ["git","-C",str(root),*args],
        capture_output=True,text=True,check=False,
    )
    if result.returncode!=0:
        raise ObservabilityEconomicsCandidateError("git identity unavailable")
    return result.stdout.strip()


def validate(root:Path=ROOT, *, head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    candidate=_load(root,CANDIDATE)
    master=_load(root,MASTER)
    frontier=_load(root,FRONTIER)
    tree=_load(root,TREE)

    if candidate.get("schema_version")!="skeleton.ai.observability_economics_gapfill_candidate.v1":
        raise ObservabilityEconomicsCandidateError("candidate schema drift")
    if candidate.get("status")!="implementation_candidate":
        raise ObservabilityEconomicsCandidateError("candidate status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED:
        raise ObservabilityEconomicsCandidateError("candidate volume identity drift")
    if candidate.get("source_queue_state")!="queued_unmodified":
        raise ObservabilityEconomicsCandidateError("candidate may not claim scheduling authority")

    promotion=candidate.get("promotion_state",{})
    for key in (
        "completion_checkbox","implementation_signed","verification_signed",
        "may_self_close","production_authority",
    ):
        if promotion.get(key) is not False:
            raise ObservabilityEconomicsCandidateError(f"candidate illegally promoted {key}")

    evidence=candidate.get("evidence_policy",{})
    for key in (
        "exact_head_ci_required","independent_closure_required",
        "queued_frontier_must_remain_unchanged",
        "canonical_ai_mirror_parity_required",
        "operations_review_required",
        "completion_may_not_be_self_granted",
    ):
        if evidence.get(key) is not True:
            raise ObservabilityEconomicsCandidateError(f"missing evidence policy: {key}")

    tranche=frontier.get("next_tranche",{})
    scheduled=set(tranche.get("scheduled_volume_refs",()))
    queued=set(tranche.get("queued_volume_refs",()))
    if set(EXPECTED)&scheduled:
        raise ObservabilityEconomicsCandidateError("observability gap-fill volumes escaped into scheduled frontier")
    if not set(EXPECTED).issubset(queued):
        raise ObservabilityEconomicsCandidateError("observability gap-fill volumes must remain explicitly queued")

    modules=candidate.get("primary_implementation_by_volume",{})
    tests=candidate.get("primary_test_by_volume",{})
    if set(modules)!=set(EXPECTED) or set(tests)!=set(EXPECTED):
        raise ObservabilityEconomicsCandidateError("per-volume module/test registry drift")

    shared_module=candidate.get("shared_integration_module")
    shared_test=candidate.get("shared_integration_test")
    if shared_module!="skeleton/observability/operations_review.py" or shared_test!="skeleton/testing/test_operations_review.py":
        raise ObservabilityEconomicsCandidateError("operations-review integration declaration drift")
    if not (root/shared_module).is_file() or not (root/shared_test).is_file():
        raise ObservabilityEconomicsCandidateError("operations-review integration evidence missing")

    volumes=master.get("volumes")
    if not isinstance(volumes,list):
        raise ObservabilityEconomicsCandidateError("masterplan volume registry missing")
    by_key={value.get("key"):value for value in volumes if isinstance(value,dict)}
    for key in EXPECTED:
        volume=by_key.get(key)
        if not isinstance(volume,dict):
            raise ObservabilityEconomicsCandidateError(f"masterplan volume missing: {key}")
        if volume.get("implementation_status")!="unverified":
            raise ObservabilityEconomicsCandidateError(
                f"{key} must remain unverified until independent exact-head closure"
            )
        if volume.get("completion_checkbox") is not False:
            raise ObservabilityEconomicsCandidateError(f"{key} completion checkbox self-promoted")
        module=modules[key]
        test=tests[key]
        paths=volume.get("implementation_paths",())
        regressions=volume.get("tests",())
        if module not in paths or shared_module not in paths:
            raise ObservabilityEconomicsCandidateError(f"{key} implementation binding drift")
        if test not in regressions or shared_test not in regressions:
            raise ObservabilityEconomicsCandidateError(f"{key} executable test binding drift")
        if any(str(item).startswith("planned:") for item in regressions):
            raise ObservabilityEconomicsCandidateError(f"{key} retains planned test placeholder")
        if not (root/module).is_file() or not (root/test).is_file():
            raise ObservabilityEconomicsCandidateError(f"{key} implementation/test file missing")
        gaps=volume.get("gaps")
        if not isinstance(gaps,list) or not gaps:
            raise ObservabilityEconomicsCandidateError(f"{key} must retain independent verification gap")

    cross=candidate.get("cross_plane_tests")
    if not isinstance(cross,list) or not cross or len(cross)!=len(set(cross)):
        raise ObservabilityEconomicsCandidateError("cross-plane test registry drift")
    for test in cross:
        if not (root/test).is_file():
            raise ObservabilityEconomicsCandidateError(f"cross-plane test missing: {test}")

    pairs=candidate.get("mirror_pairs")
    if not isinstance(pairs,list) or len(pairs)!=9:
        raise ObservabilityEconomicsCandidateError("mirror pair registry drift")
    for pair in pairs:
        if not isinstance(pair,list) or len(pair)!=2:
            raise ObservabilityEconomicsCandidateError("invalid mirror pair declaration")
        left,right=(root/pair[0],root/pair[1])
        if not left.is_file() or not right.is_file():
            raise ObservabilityEconomicsCandidateError(f"mirror file missing: {pair}")
        if left.read_bytes()!=right.read_bytes():
            raise ObservabilityEconomicsCandidateError(f"mirror parity drift: {pair[0]}")

    mappings=tree.get("mappings")
    if not isinstance(mappings,list):
        raise ObservabilityEconomicsCandidateError("AI file-tree mapping registry missing")
    mapping=next((item for item in mappings if isinstance(item,dict) and item.get("id")=="AIFT-OBSERVABILITY"),None)
    if not isinstance(mapping,dict):
        raise ObservabilityEconomicsCandidateError("AIFT-OBSERVABILITY mapping missing")
    if mapping.get("source")!="skeleton/observability" or mapping.get("destination")!="skeleton/ai/runtime/observability":
        raise ObservabilityEconomicsCandidateError("AIFT-OBSERVABILITY root identity drift")
    if not set(EXPECTED).issubset(set(mapping.get("volume_refs",()))):
        raise ObservabilityEconomicsCandidateError("AIFT-OBSERVABILITY volume coverage drift")

    source_tree=_git(root,"rev-parse","HEAD:skeleton/observability")
    if mapping.get("source_git_object_sha")!=source_tree:
        raise ObservabilityEconomicsCandidateError("AIFT-OBSERVABILITY source tree identity drift")

    actual_head=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual_head) is None:
        raise ObservabilityEconomicsCandidateError("checkout HEAD identity malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None:
            raise ObservabilityEconomicsCandidateError("reported exact head malformed")
        if head!=actual_head:
            raise ObservabilityEconomicsCandidateError("reported exact head does not match checkout")

    return {
        "status":"valid",
        "candidate_id":candidate["candidate_id"],
        "volume_refs":list(EXPECTED),
        "volume_count":len(EXPECTED),
        "primary_test_count":len(EXPECTED),
        "cross_plane_test_count":len(cross),
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
    except ObservabilityEconomicsCandidateError as exc:
        print(f"observability economics gap-fill candidate: FAIL: {exc}",file=sys.stderr)
        return 1
    print(json.dumps(result,indent=2,sort_keys=True) if args.json else "observability economics gap-fill candidate: OK")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
