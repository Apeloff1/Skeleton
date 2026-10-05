#!/usr/bin/env python3
"""Validate the dependency-ordered P3-T2 training/learning/multimodal candidate batch."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from scripts.p3t2_candidate_common import (
        LEARNING,
        MULTIMODAL,
        ROOT,
        TRAINING,
        P3T2CandidateError,
        validate_candidate,
    )
except ModuleNotFoundError:  # direct script execution
    from p3t2_candidate_common import (
        LEARNING,
        MULTIMODAL,
        ROOT,
        TRAINING,
        P3T2CandidateError,
        validate_candidate,
    )


EXPECTED_UNION = tuple(f"VOL-{value:03d}" for value in range(143, 160))


def validate(root=ROOT, *, head=None):
    training = validate_candidate(TRAINING, root, head=head)
    learning = validate_candidate(LEARNING, root, head=head)
    multimodal = validate_candidate(MULTIMODAL, root, head=head)
    results = (training, learning, multimodal)

    heads = {result["actual_head"] for result in results}
    if len(heads) != 1:
        raise P3T2CandidateError("candidate batch is not bound to one exact checkout")
    refs = [
        volume
        for result in results
        for volume in result["volume_refs"]
    ]
    if len(refs) != len(set(refs)):
        raise P3T2CandidateError("candidate batch volume ownership overlaps")
    if tuple(refs) != EXPECTED_UNION:
        raise P3T2CandidateError("candidate batch must cover exact VOL-143..VOL-159 sequence")
    if training["dependency_task_ids"] != ["P3T2-DATA-01"]:
        raise P3T2CandidateError("training dependency chain drift")
    if learning["dependency_task_ids"] != ["P3T2-TRAINING-01"]:
        raise P3T2CandidateError("learning dependency chain drift")
    if multimodal["dependency_task_ids"] != [
        "P3T2-DATA-01",
        "P3T2-TRAINING-01",
        "P3T2-LEARNING-01",
    ]:
        raise P3T2CandidateError("multimodal dependency chain drift")

    return {
        "status": "valid",
        "task_ids": [result["task_id"] for result in results],
        "volume_refs": refs,
        "volume_count": len(refs),
        "implementation_module_count": sum(
            result["implementation_module_count"] for result in results
        ),
        "executable_test_count": sum(
            result["executable_test_count"] for result in results
        ),
        "cross_plane_test_count": sum(
            result["cross_plane_test_count"] for result in results
        ),
        "mirror_pair_count": sum(
            result["mirror_pair_count"] for result in results
        ),
        "actual_head": training["actual_head"],
        "completion_checkbox": False,
        "promotion_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT, head=args.head)
    except P3T2CandidateError as exc:
        print("P3-T2 continuation candidate batch: FAIL: " + str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("P3-T2 continuation candidate batch: OK (17 volumes; no closure authority)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
