#!/usr/bin/env python3
"""Validate the P3-T2 training implementation candidate without granting closure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
FRONTIER = Path("machine/ai_masterplan_continuation_frontier.json")
MASTER = Path("machine/ai_master_plan.json")
CANDIDATE = Path("machine/ai_p3t2_training_candidate.json")
EXPECTED_VOLUMES = (
    "VOL-143",
    "VOL-144",
    "VOL-145",
    "VOL-146",
    "VOL-147",
    "VOL-148",
    "VOL-149",
)
MIRRORS = (
    ("skeleton/training/p3t2_ledger.py", "skeleton/ai/runtime/training/p3t2_ledger.py"),
)
TESTS = ("skeleton/testing/test_training_control.py",)


class TrainingCandidateError(RuntimeError):
    pass


def _load(root: Path, rel: Path) -> dict[str, Any]:
    try:
        value = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingCandidateError(f"cannot read {rel}") from exc
    if not isinstance(value, dict):
        raise TrainingCandidateError(f"{rel} must contain an object")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    frontier = _load(root, FRONTIER)
    master = _load(root, MASTER)
    candidate = _load(root, CANDIDATE)
    if candidate.get("schema_version") != "skeleton.ai.p3t2.training_candidate.v1":
        raise TrainingCandidateError("training candidate schema drift")
    if candidate.get("status") != "implementation_candidate":
        raise TrainingCandidateError("training lane must remain an implementation candidate")
    if tuple(candidate.get("volume_refs", ())) != EXPECTED_VOLUMES:
        raise TrainingCandidateError("training candidate volume ownership drift")
    tranche = frontier.get("next_tranche", {})
    if tranche.get("status") != "planned":
        raise TrainingCandidateError("P3-T2 frontier must remain planned")
    owners = tranche.get("planned_task_owners")
    if not isinstance(owners, list):
        raise TrainingCandidateError("P3-T2 owner registry missing")
    owner = next(
        (x for x in owners if isinstance(x, dict) and x.get("task_id") == "P3T2-TRAINING-01"),
        None,
    )
    if owner is None:
        raise TrainingCandidateError("P3T2-TRAINING-01 owner missing")
    if owner.get("planning_status") != "planned":
        raise TrainingCandidateError("training owner must remain planned")
    if tuple(owner.get("primary_volume_refs", ())) != EXPECTED_VOLUMES:
        raise TrainingCandidateError("training owner volume identity drift")
    for key in ("completion_checkbox", "implementation_signed", "verification_signed"):
        if owner.get(key) is not False:
            raise TrainingCandidateError(f"planning owner illegally promoted {key}")
    if owner.get("implementation_candidate") is not None:
        raise TrainingCandidateError(
            "training candidate must not be written into the continuation owner registry by this packet"
        )
    promotion = candidate.get("promotion_state", {})
    for key in ("completion_checkbox", "implementation_signed", "verification_signed", "may_self_close"):
        if promotion.get(key) is not False:
            raise TrainingCandidateError(f"candidate illegally promoted {key}")
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise TrainingCandidateError("master plan volumes missing")
    keys = {v.get("key") for v in volumes if isinstance(v, dict)}
    missing = [key for key in EXPECTED_VOLUMES if key not in keys]
    if missing:
        raise TrainingCandidateError("unknown training volumes: " + ",".join(missing))
    declared = candidate.get("exact_mirror_pairs")
    if declared != [list(pair) for pair in MIRRORS]:
        raise TrainingCandidateError("declared training mirror pairs drift")
    for source, destination in MIRRORS:
        left = root / source
        right = root / destination
        if not left.is_file() or not right.is_file():
            raise TrainingCandidateError(f"training mirror file missing: {source} -> {destination}")
        if left.read_bytes() != right.read_bytes():
            raise TrainingCandidateError(f"training mirror parity drift: {source} -> {destination}")
    if tuple(candidate.get("executable_tests", ())) != TESTS:
        raise TrainingCandidateError("training executable test registry drift")
    for test_path in TESTS:
        if not (root / test_path).is_file():
            raise TrainingCandidateError(f"candidate test missing: {test_path}")
    return {
        "status": "valid",
        "task_id": "P3T2-TRAINING-01",
        "volume_count": 7,
        "volume_refs": list(EXPECTED_VOLUMES),
        "mirror_pair_count": 2,
        "completion_checkbox": False,
        "implementation_signed": False,
        "verification_signed": False,
        "promotion_authority": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(ROOT)
    except TrainingCandidateError as exc:
        print(f"P3-T2 training candidate: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else "P3-T2 training candidate: OK (7 volumes, no closure authority)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
