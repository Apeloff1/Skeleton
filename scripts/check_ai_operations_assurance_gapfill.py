#!/usr/bin/env python3
"""Validate the VOL-188..VOL-200 operations-assurance gap-fill candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=Path("machine/ai_operations_assurance_gapfill_candidate.json")
BLOCKER=Path("machine/ai_vol195_local_development_blocker.json")
MASTER=Path("machine/ai_master_plan.json")
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
TREE=Path("machine/ai_file_tree.json")
EXPECTED=(
    "VOL-188","VOL-189","VOL-190","VOL-191","VOL-192","VOL-193",
    "VOL-194","VOL-196","VOL-197","VOL-198","VOL-199","VOL-200",
)
BLOCKED="VOL-195"


class OperationsAssuranceCandidateError(RuntimeError):
    pass


def _load(root:Path,path:Path)->dict[str,Any]:
    try:
        value=json.loads((root/path).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise OperationsAssuranceCandidateError(f"cannot read {path}") from exc
    if not isinstance(value,dict):
        raise OperationsAssuranceCandidateError(f"{path} must contain an object")
    return value


def _git(root:Path,*args:str)->str:
    result=subprocess.run(
        ["git","-C",str(root),*args],
        capture_output=True,text=True,check=False,
    )
    if result.returncode!=0:
        raise OperationsAssuranceCandidateError("git identity unavailable")
    return result.stdout.strip()


def validate(root:Path=ROOT, *, head:str|None=None)->dict[str,Any]:
    root=Path(root).resolve()
    candidate=_load(root,CANDIDATE)
    blocker=_load(root,BLOCKER)
    master=_load(root,MASTER)
    frontier=_load(root,FRONTIER)
    tree=_load(root,TREE)

    if candidate.get("schema_version")!="skeleton.ai.operations_assurance_gapfill_candidate.v1":
        raise OperationsAssuranceCandidateError("candidate schema drift")
    if candidate.get("status")!="implementation_candidate":
        raise OperationsAssuranceCandidateError("candidate status drift")
    if tuple(candidate.get("volume_refs",()))!=EXPECTED:
        raise OperationsAssuranceCandidateError("candidate volume identity drift")
    if candidate.get("source_queue_state")!="queued_unmodified":
        raise OperationsAssuranceCandidateError("candidate may not claim scheduling authority")
    if BLOCKED in set(EXPECTED):
        raise OperationsAssuranceCandidateError("blocked volume leaked into candidate")

    excluded=candidate.get("excluded_blocker",{})
    if excluded.get("volume_ref")!=BLOCKED:
        raise OperationsAssuranceCandidateError("VOL-195 blocker identity drift")
    if excluded.get("receipt")!=str(BLOCKER):
        raise OperationsAssuranceCandidateError("VOL-195 blocker receipt drift")
    if excluded.get("must_remain_unverified") is not True:
        raise OperationsAssuranceCandidateError("VOL-195 must remain unverified")
    if excluded.get("required_missing_artifact")!="uv.lock":
        raise OperationsAssuranceCandidateError("VOL-195 blocking artifact drift")

    if blocker.get("schema_version")!="skeleton.ai.local_development_blocker.v1":
        raise OperationsAssuranceCandidateError("VOL-195 blocker schema drift")
    if blocker.get("volume_ref")!=BLOCKED or blocker.get("status")!="blocked":
        raise OperationsAssuranceCandidateError("VOL-195 blocker state drift")
    if blocker.get("blocking_artifact")!="uv.lock":
        raise OperationsAssuranceCandidateError("VOL-195 blocker artifact drift")
    if (root/"uv.lock").exists():
        raise OperationsAssuranceCandidateError(
            "VOL-195 blocker is stale because uv.lock now exists"
        )
    fail_closed=blocker.get("fail_closed_behavior",{})
    for key in (
        "bootstrap_refuses_missing_lock",
    ):
        if fail_closed.get(key) is not True:
            raise OperationsAssuranceCandidateError(f"VOL-195 missing fail-closed marker: {key}")
    for key in (
        "unlocked_resolution_allowed","completion_checkbox",
        "implementation_signed","verification_signed","production_authority",
    ):
        if fail_closed.get(key) is not False:
            raise OperationsAssuranceCandidateError(f"VOL-195 illegally promoted: {key}")

    promotion=candidate.get("promotion_state",{})
    for key in (
        "completion_checkbox","implementation_signed","verification_signed",
        "may_self_close","production_authority",
    ):
        if promotion.get(key) is not False:
            raise OperationsAssuranceCandidateError(f"candidate illegally promoted {key}")

    policy=candidate.get("evidence_policy",{})
    for key in (
        "exact_head_ci_required","independent_closure_required",
        "queued_frontier_must_remain_unchanged",
        "blocked_volume_must_not_be_promoted",
        "completion_may_not_be_self_granted",
    ):
        if policy.get(key) is not True:
            raise OperationsAssuranceCandidateError(f"missing evidence policy: {key}")

    tranche=frontier.get("next_tranche",{})
    scheduled=set(tranche.get("scheduled_volume_refs",()))
    queued=set(tranche.get("queued_volume_refs",()))
    all_deferred=set(EXPECTED)|{BLOCKED}
    if all_deferred & scheduled:
        raise OperationsAssuranceCandidateError(
            "operations-assurance volumes escaped into scheduled frontier"
        )
    if not all_deferred.issubset(queued):
        raise OperationsAssuranceCandidateError(
            "operations-assurance volumes must remain explicitly queued"
        )

    volumes=master.get("volumes")
    if not isinstance(volumes,list):
        raise OperationsAssuranceCandidateError("masterplan volume registry missing")
    by_key={item.get("key"):item for item in volumes if isinstance(item,dict)}

    blocked_volume=by_key.get(BLOCKED)
    if not isinstance(blocked_volume,dict):
        raise OperationsAssuranceCandidateError("VOL-195 missing from masterplan")
    if blocked_volume.get("implementation_status")!="unverified":
        raise OperationsAssuranceCandidateError("VOL-195 blocker may not be promoted")
    if blocked_volume.get("completion_checkbox") is not False:
        raise OperationsAssuranceCandidateError("VOL-195 completion self-promoted")
    if str(BLOCKER) not in set(blocked_volume.get("evidence",())):
        raise OperationsAssuranceCandidateError("VOL-195 blocker receipt not bound to masterplan")
    gaps=blocked_volume.get("gaps")
    if not isinstance(gaps,list) or not any("uv.lock" in str(item) for item in gaps):
        raise OperationsAssuranceCandidateError("VOL-195 lockfile blocker not explicit in gaps")

    primary_impl=candidate.get("primary_implementation_by_volume",{})
    primary_test=candidate.get("primary_test_by_volume",{})
    if set(primary_impl)!=set(EXPECTED) or set(primary_test)!=set(EXPECTED):
        raise OperationsAssuranceCandidateError("primary implementation/test registry drift")
    gapfill_impl=candidate.get("gapfill_implementation")
    gapfill_test=candidate.get("gapfill_test")
    if gapfill_impl!="skeleton/ai/runtime/deferred/operations_assurance.py":
        raise OperationsAssuranceCandidateError("gapfill implementation identity drift")
    if gapfill_test!="skeleton/testing/test_operations_assurance_gapfill.py":
        raise OperationsAssuranceCandidateError("gapfill test identity drift")
    if not (root/gapfill_impl).is_file() or not (root/gapfill_test).is_file():
        raise OperationsAssuranceCandidateError("gapfill implementation/test missing")

    for key in EXPECTED:
        volume=by_key.get(key)
        if not isinstance(volume,dict):
            raise OperationsAssuranceCandidateError(f"masterplan volume missing: {key}")
        if volume.get("implementation_status")!="implemented":
            raise OperationsAssuranceCandidateError(f"{key} must remain implemented")
        if volume.get("completion_checkbox") is not False:
            raise OperationsAssuranceCandidateError(f"{key} completion checkbox self-promoted")
        paths=set(volume.get("implementation_paths",()))
        tests=set(volume.get("tests",()))
        if primary_impl[key] not in paths:
            raise OperationsAssuranceCandidateError(f"{key} primary implementation path drift")
        if gapfill_impl not in paths and key!="VOL-196":
            raise OperationsAssuranceCandidateError(f"{key} missing operations-assurance gapfill path")
        if primary_test[key] not in tests:
            raise OperationsAssuranceCandidateError(f"{key} primary test path drift")
        if gapfill_test not in tests and key!="VOL-196":
            raise OperationsAssuranceCandidateError(f"{key} missing shared gapfill regression")
        if any(str(item).startswith("planned:") for item in tests):
            raise OperationsAssuranceCandidateError(f"{key} retains planned test placeholder")
        if not (root/primary_impl[key]).is_file() or not (root/primary_test[key]).is_file():
            raise OperationsAssuranceCandidateError(f"{key} primary implementation/test missing")
        gaps=volume.get("gaps")
        if not isinstance(gaps,list):
            raise OperationsAssuranceCandidateError(f"{key} gaps must remain explicit")
        if key!="VOL-196" and not any("independent exact-head" in str(item) for item in gaps):
            raise OperationsAssuranceCandidateError(
                f"{key} must retain independent exact-head verification gap"
            )

    mappings=tree.get("mappings")
    if not isinstance(mappings,list):
        raise OperationsAssuranceCandidateError("AI file-tree mapping registry missing")
    by_id={item.get("id"):item for item in mappings if isinstance(item,dict)}
    for volume_ref,mapping_id in candidate.get("mapping_requirements",{}).items():
        mapping=by_id.get(mapping_id)
        if not isinstance(mapping,dict):
            raise OperationsAssuranceCandidateError(f"required mapping missing: {mapping_id}")
        if volume_ref not in set(mapping.get("volume_refs",())):
            raise OperationsAssuranceCandidateError(
                f"{mapping_id} does not own {volume_ref}"
            )

    actual_head=_git(root,"rev-parse","HEAD")
    if re.fullmatch(r"[0-9a-f]{40}",actual_head) is None:
        raise OperationsAssuranceCandidateError("checkout HEAD identity malformed")
    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None:
            raise OperationsAssuranceCandidateError("reported exact head malformed")
        if head!=actual_head:
            raise OperationsAssuranceCandidateError(
                "reported exact head does not match checkout"
            )

    return {
        "status":"valid",
        "candidate_id":candidate["candidate_id"],
        "volume_refs":list(EXPECTED),
        "volume_count":len(EXPECTED),
        "blocked_volume":BLOCKED,
        "blocked_artifact":"uv.lock",
        "queued_frontier_preserved":True,
        "actual_head":actual_head,
        "reported_head":head,
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
    except OperationsAssuranceCandidateError as exc:
        print(f"operations assurance gap-fill candidate: FAIL: {exc}",file=sys.stderr)
        return 1
    print(
        json.dumps(result,indent=2,sort_keys=True)
        if args.json else "operations assurance gap-fill candidate: OK"
    )
    return 0


if __name__=="__main__":
    raise SystemExit(main())
