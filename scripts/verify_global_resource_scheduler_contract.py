#!/usr/bin/env python3
"""Fail-closed verifier for G021 global resource scheduling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.kernel.global_resource_scheduler import ResourceVector


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    path = ROOT / "machine/global_resource_scheduler_contract.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"G021 scheduler: rejected: {exc}", file=sys.stderr)
        return 2

    if contract.get("schema_version") != "skeleton.ai.global_resource_scheduler_contract.v1":
        errors.append("G021 scheduler schema drift")
    if contract.get("status") != "active":
        errors.append("G021 scheduler contract must be active")
    if contract.get("gap_id") != "G021":
        errors.append("G021 gap identity drift")
    if contract.get("completion_authority") is not False:
        errors.append("G021 implementation cannot self-grant completion")

    expected_dimensions = sorted(ResourceVector().as_dict())
    if contract.get("resource_dimensions") != expected_dimensions:
        errors.append("G021 resource dimension drift")

    canonical = ROOT / "skeleton/kernel/global_resource_scheduler.py"
    mirror = ROOT / "skeleton/ai/runtime/kernel/global_resource_scheduler.py"
    if not canonical.is_file() or not mirror.is_file():
        errors.append("G021 canonical or governed AI runtime is missing")
    elif canonical.read_bytes() != mirror.read_bytes():
        errors.append("G021 canonical/governed AI runtime drift")

    swarm = ROOT / "skeleton/automation/agents/scheduler.py"
    swarm_mirror = ROOT / "skeleton/ai/agents/core/scheduler.py"
    if not swarm.is_file() or not swarm_mirror.is_file():
        errors.append("G021 swarm integration surface is missing")
    elif swarm.read_bytes() != swarm_mirror.read_bytes():
        errors.append("G021 swarm canonical/governed AI mirror drift")
    else:
        swarm_source = swarm.read_text(encoding="utf-8")
        for bridge_marker in (
            "global_resources",
            "ResourceRequest",
            "_resource_request_id",
            "resource_epoch",
        ):
            if bridge_marker not in swarm_source:
                errors.append(
                    f"G021 swarm integration missing marker: {bridge_marker}"
                )

    if canonical.is_file():
        source = canonical.read_text(encoding="utf-8")
        for marker in (
            "def admit_next",
            "def admit_request",
            "def begin_preemption",
            "def ack_preempted",
            "def _effective_priority",
            "def _plane_has_queued_demand",
            "completion_checkbox",
        ):
            if marker not in source:
                errors.append(f"G021 canonical runtime missing marker: {marker}")

    result = {
        "schema_version": "skeleton.ai.global_resource_scheduler_verifier.v1",
        "gap_id": "G021",
        "valid": not errors,
        "resource_dimension_count": len(expected_dimensions),
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
    else:
        print("G021 global resource scheduler: OK")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
