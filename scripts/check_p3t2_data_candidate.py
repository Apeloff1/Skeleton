#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ("VOL-137", "VOL-138", "VOL-139", "VOL-140", "VOL-141", "VOL-142")
TESTS = {
    "VOL-137": "skeleton/testing/test_data_ingestion.py",
    "VOL-138": "skeleton/testing/test_document_intelligence.py",
    "VOL-139": "skeleton/testing/test_data_lineage.py",
    "VOL-140": "skeleton/testing/test_data_quality.py",
    "VOL-141": "skeleton/testing/test_dataset_registry.py",
    "VOL-142": "skeleton/testing/test_synthetic_data_factory.py",
}
MODULES = {
    "VOL-137": "skeleton/data/ingestion.py",
    "VOL-138": "skeleton/data/document_intelligence.py",
    "VOL-139": "skeleton/data/lineage_governance.py",
    "VOL-140": "skeleton/data/quality.py",
    "VOL-141": "skeleton/data/dataset_registry.py",
    "VOL-142": "skeleton/data/synthetic.py",
}


class DataCandidateError(RuntimeError):
    pass


def load(root: Path, path: str):
    try:
        return json.loads((root / path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise DataCandidateError(f"cannot read {path}") from exc


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DataCandidateError("git identity unavailable")
    return result.stdout.strip()


def validate(root=ROOT, head=None):
    root = Path(root).resolve()
    frontier = load(root, "machine/ai_masterplan_continuation_frontier.json")
    master = load(root, "machine/ai_master_plan.json")
    tree = load(root, "machine/ai_file_tree.json")
    storage = load(root, "machine/ai_p3t2_storage_candidate.json")
    candidate = load(root, "machine/ai_p3t2_data_candidate.json")

    if candidate.get("status") != "implementation_candidate":
        raise DataCandidateError("candidate status drift")
    if (
        storage.get("status") != "implementation_candidate"
        or storage.get("task_id") != "P3T2-STORAGE-01"
        or candidate.get("stacked_on_task_id") != "P3T2-STORAGE-01"
    ):
        raise DataCandidateError("storage dependency drift")

    owner = next(
        (
            item
            for item in frontier["next_tranche"]["planned_task_owners"]
            if item.get("task_id") == "P3T2-DATA-01"
        ),
        None,
    )
    if (
        owner is None
        or owner.get("planning_status") != "planned"
        or owner.get("depends_on") != ["P3T2-STORAGE-01"]
        or tuple(owner.get("primary_volume_refs", ())) != EXPECTED
        or tuple(candidate.get("volume_refs", ())) != EXPECTED
    ):
        raise DataCandidateError("owner/dependency drift")

    for key in ("completion_checkbox", "implementation_signed", "verification_signed"):
        if owner.get(key) is not False or candidate["promotion_state"].get(key) is not False:
            raise DataCandidateError("illegal promotion")
    if candidate["promotion_state"].get("may_self_close") is not False:
        raise DataCandidateError("illegal self-close authority")

    evidence_policy = candidate.get("evidence_policy", {})
    for key in (
        "exact_head_ci_required",
        "independent_closure_required",
        "current_main_reconciliation_required",
        "storage_dependency_candidate_required",
    ):
        if evidence_policy.get(key) is not True:
            raise DataCandidateError("evidence policy drift")

    expected_modules = tuple(MODULES[key] for key in EXPECTED)
    expected_tests = tuple(TESTS[key] for key in EXPECTED)
    expected_pairs = tuple(
        (
            module,
            module.replace("skeleton/data/", "skeleton/ai/runtime/data/", 1),
        )
        for module in expected_modules
    )
    if (
        tuple(candidate.get("implementation_modules", ())) != expected_modules
        or tuple(candidate.get("executable_tests", ())) != expected_tests
        or tuple(tuple(pair) for pair in candidate.get("mirror_pairs", ()))
        != expected_pairs
        or candidate.get("source_root") != "skeleton/data"
        or candidate.get("mirror_root") != "skeleton/ai/runtime/data"
    ):
        raise DataCandidateError("candidate declaration drift")

    volumes = {volume.get("key"): volume for volume in master["volumes"]}
    for key in EXPECTED:
        volume = volumes.get(key)
        if volume is None:
            raise DataCandidateError(f"{key} missing")
        module = MODULES[key]
        test = TESTS[key]
        if (
            volume.get("completion_checkbox") is not False
            or volume.get("implementation_status") == "verified"
        ):
            raise DataCandidateError(f"{key} completion drift")
        if (
            module not in volume.get("implementation_paths", [])
            or test not in volume.get("tests", [])
            or f"planned:{test}" in volume.get("tests", [])
        ):
            raise DataCandidateError(f"{key} implementation/test drift")
        if not (root / module).is_file() or not (root / test).is_file():
            raise DataCandidateError(f"{key} implementation evidence missing")

    mapping = next(
        (item for item in tree["mappings"] if item.get("id") == "AIFT-DATA"),
        None,
    )
    if mapping is None or not set(EXPECTED).issubset(set(mapping.get("volume_refs", []))):
        raise DataCandidateError("AIFT-DATA volume drift")

    actual_head = _git(root, "rev-parse", "HEAD")
    actual_data_tree = _git(root, "rev-parse", "HEAD:skeleton/data")
    if mapping.get("source_git_object_sha") != actual_data_tree:
        raise DataCandidateError("AIFT-DATA source tree identity drift")
    reconciliation = tree.get("reconciliation", {}).get("p3t2_data_candidate", {})
    if reconciliation.get("source_tree_sha") != actual_data_tree:
        raise DataCandidateError("P3-T2 data reconciliation tree drift")
    implementation_head = reconciliation.get("implementation_head_sha")
    if (
        not isinstance(implementation_head, str)
        or re.fullmatch(r"[0-9a-f]{40}", implementation_head) is None
    ):
        raise DataCandidateError("P3-T2 implementation head identity drift")
    implementation_available = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "cat-file",
            "-e",
            f"{implementation_head}^{commit}",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).returncode == 0
    if implementation_available:
        implementation_tree = _git(
            root,
            "rev-parse",
            f"{implementation_head}:skeleton/data",
        )
        if implementation_tree != actual_data_tree:
            raise DataCandidateError("P3-T2 implementation tree identity drift")

        ancestor = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                implementation_head,
                actual_head,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if ancestor.returncode != 0:
            # Reconciliation may preserve the implementation byte-for-byte
            # without preserving the historical commit as an ancestor. The
            # immutable source-tree identity above is the authority boundary.
            if reconciliation.get("source_tree_sha") != implementation_tree:
                raise DataCandidateError(
                    "P3-T2 reconciled implementation tree identity drift"
                )
    elif reconciliation.get("source_tree_sha") != actual_data_tree:
        raise DataCandidateError(
            "P3-T2 implementation commit unavailable without exact tree binding"
        )

    for left, right in expected_pairs:
        if (root / left).read_bytes() != (root / right).read_bytes():
            raise DataCandidateError(f"mirror drift: {left}")

    if head is not None:
        if re.fullmatch(r"[0-9a-f]{40}", head) is None:
            raise DataCandidateError("invalid exact head")
        if head != actual_head:
            raise DataCandidateError("exact head mismatch")

    return {
        "status": "valid",
        "task_id": "P3T2-DATA-01",
        "volume_count": len(EXPECTED),
        "test_count": len(expected_tests),
        "mirror_count": len(expected_pairs),
        "completion_checkbox": False,
        "reported_head": head,
        "source_tree_sha": actual_data_tree,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT, head=args.head)
    except DataCandidateError as exc:
        print(f"P3-T2 data candidate: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(result, indent=2, sort_keys=True)
        if args.json
        else "P3-T2 data candidate: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
