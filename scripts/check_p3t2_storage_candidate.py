#!/usr/bin/env python3
"""Validate the P3-T2 governed-storage implementation candidate without granting closure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

ROOT=Path(__file__).resolve().parents[1]
FRONTIER=Path("machine/ai_masterplan_continuation_frontier.json")
MASTER=Path("machine/ai_master_plan.json")
TREE=Path("machine/ai_file_tree.json")
CANDIDATE=Path("machine/ai_p3t2_storage_candidate.json")
EXPECTED_VOLUMES=("VOL-133","VOL-135","VOL-136")
EXPECTED_TESTS={
    "VOL-133":"skeleton/testing/test_distributed_transactions.py",
    "VOL-135":"skeleton/testing/test_cache_architecture.py",
    "VOL-136":"skeleton/testing/test_content_addressing.py",
}
MIRRORS=(
    ("skeleton/storage/__init__.py","skeleton/ai/runtime/storage/__init__.py"),
    ("skeleton/storage/cas/__init__.py","skeleton/ai/runtime/storage/cas/__init__.py"),
)

class StorageCandidateError(RuntimeError):
    pass

def _load(root:Path, rel:Path)->dict[str,Any]:
    try:
        value=json.loads((root/rel).read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:
        raise StorageCandidateError(f"cannot read {rel}") from exc
    if not isinstance(value,dict):
        raise StorageCandidateError(f"{rel} must contain an object")
    return value

def validate(root:Path=ROOT, *, head:str|None=None)->dict[str,Any]:
    root=root.resolve()
    frontier=_load(root,FRONTIER)
    master=_load(root,MASTER)
    tree=_load(root,TREE)
    candidate=_load(root,CANDIDATE)

    if candidate.get("schema_version")!="skeleton.ai.p3t2.storage_candidate.v1":
        raise StorageCandidateError("storage candidate schema drift")
    if candidate.get("status")!="implementation_candidate":
        raise StorageCandidateError("storage lane must remain an implementation candidate")

    tranche=frontier.get("next_tranche",{})
    if tranche.get("status")!="planned":
        raise StorageCandidateError("P3-T2 frontier must remain planned")
    owners=tranche.get("planned_task_owners")
    if not isinstance(owners,list):
        raise StorageCandidateError("P3-T2 owner registry missing")
    owner=next((x for x in owners if isinstance(x,dict) and x.get("task_id")=="P3T2-STORAGE-01"),None)
    if owner is None:
        raise StorageCandidateError("P3T2-STORAGE-01 owner missing")
    if owner.get("lane_id")!="P3T2-L0" or owner.get("planning_status")!="planned":
        raise StorageCandidateError("storage owner planning identity drift")
    if tuple(owner.get("primary_volume_refs",()))!=EXPECTED_VOLUMES:
        raise StorageCandidateError("storage owner volume identity drift")
    for key in ("completion_checkbox","implementation_signed","verification_signed"):
        if owner.get(key) is not False:
            raise StorageCandidateError(f"planning owner illegally promoted {key}")

    if tuple(candidate.get("volume_refs",()))!=EXPECTED_VOLUMES:
        raise StorageCandidateError("candidate volume ownership drift")
    if candidate.get("task_id")!="P3T2-STORAGE-01" or candidate.get("lane_id")!="P3T2-L0":
        raise StorageCandidateError("candidate task/lane identity drift")

    promotion=candidate.get("promotion_state",{})
    for key in ("completion_checkbox","implementation_signed","verification_signed","may_self_close"):
        if promotion.get(key) is not False:
            raise StorageCandidateError(f"candidate illegally promoted {key}")
    evidence=candidate.get("evidence_policy",{})
    for key in ("exact_head_ci_required","checked_out_head_must_be_reported","independent_closure_required","current_main_reconciliation_required"):
        if evidence.get(key) is not True:
            raise StorageCandidateError(f"missing evidence policy: {key}")

    volumes=master.get("volumes")
    if not isinstance(volumes,list):
        raise StorageCandidateError("master plan volumes missing")
    by_key={v.get("key"):v for v in volumes if isinstance(v,dict)}
    for key in EXPECTED_VOLUMES:
        volume=by_key.get(key)
        if not isinstance(volume,dict):
            raise StorageCandidateError(f"masterplan volume missing: {key}")
        if volume.get("completion_checkbox") is not False:
            raise StorageCandidateError(f"{key} completion checkbox may not self-promote")
        if volume.get("implementation_status")=="verified":
            raise StorageCandidateError(f"{key} may not claim verified implementation from this candidate")
        paths=volume.get("implementation_paths")
        if not isinstance(paths,list) or "skeleton/storage/cas" not in paths:
            raise StorageCandidateError(f"{key} missing governed storage implementation path")
        tests=volume.get("tests")
        expected=EXPECTED_TESTS[key]
        if not isinstance(tests,list) or expected not in tests:
            raise StorageCandidateError(f"{key} missing executable storage regression")
        if f"planned:{expected}" in tests:
            raise StorageCandidateError(f"{key} still labels executable regression as planned")

    mappings=tree.get("mappings")
    if not isinstance(mappings,list):
        raise StorageCandidateError("AI file-tree mapping registry missing")
    mapping=next((x for x in mappings if isinstance(x,dict) and x.get("id")=="AIFT-STORAGE"),None)
    if mapping is None:
        raise StorageCandidateError("AIFT-STORAGE mapping missing")
    if mapping.get("source")!="skeleton/storage" or mapping.get("destination")!="skeleton/ai/runtime/storage":
        raise StorageCandidateError("AIFT-STORAGE source/destination drift")
    if tuple(mapping.get("volume_refs",()))!=EXPECTED_VOLUMES:
        raise StorageCandidateError("AIFT-STORAGE volume identity drift")

    declared_pairs=candidate.get("exact_mirror_pairs")
    if declared_pairs!=[list(pair) for pair in MIRRORS]:
        raise StorageCandidateError("declared storage mirror pairs drift")
    for source,destination in MIRRORS:
        left=root/source
        right=root/destination
        if not left.is_file() or not right.is_file():
            raise StorageCandidateError(f"storage mirror file missing: {source} -> {destination}")
        if left.read_bytes()!=right.read_bytes():
            raise StorageCandidateError(f"storage mirror parity drift: {source} -> {destination}")

    declared_tests=candidate.get("executable_tests")
    if declared_tests!=[EXPECTED_TESTS[key] for key in EXPECTED_VOLUMES]:
        raise StorageCandidateError("candidate executable test registry drift")
    for test_path in declared_tests:
        if not (root/test_path).is_file():
            raise StorageCandidateError(f"candidate test missing: {test_path}")

    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}",head) is None:
            raise StorageCandidateError("reported exact head is not a 40-character lowercase Git SHA")

    return {
        "status":"valid",
        "task_id":"P3T2-STORAGE-01",
        "volume_count":3,
        "volume_refs":list(EXPECTED_VOLUMES),
        "executable_test_count":3,
        "mirror_pair_count":2,
        "completion_checkbox":False,
        "implementation_signed":False,
        "verification_signed":False,
        "reported_head":head,
    }

def main(argv:Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head")
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=validate(ROOT,head=args.head)
    except StorageCandidateError as exc:
        print(f"P3-T2 storage candidate: FAIL: {exc}",file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result,indent=2,sort_keys=True))
    else:
        print("P3-T2 storage candidate: OK (3 volumes, 3 tests, 2 exact mirrors, no closure authority)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
