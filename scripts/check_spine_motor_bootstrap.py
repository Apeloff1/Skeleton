#!/usr/bin/env python3
"""Fail-closed structural control for the driver-injected Motor bootstrap seam."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class MotorBootstrapControlError(RuntimeError):
    """The bootstrap contract or its no-driver-import boundary drifted."""


FILES = (
    "spine_motor_plan.py",
    "spine_motor_bootstrap.py",
    "spine_motor_bootstrap_verify.py",
    "spine_motor_bootstrap_replay.py",
    "spine_motor_preflight.py",
    "spine_motor_preflight_verify.py",
    "spine_runtime_selection.py",
    "spine_runtime_selection_verify.py",
    "spine_cutover_rehearsal.py",
    "spine_cutover_rehearsal_verify.py",
    "spine_cutover_authorization.py",
    "spine_cutover_authorization_verify.py",
    "spine_cutover_effectiveness.py",
    "spine_cutover_effectiveness_verify.py",
    "spine_selection_permit.py",
    "spine_selection_permit_verify.py",
)


def verify_no_driver_imports(root: Path) -> list[str]:
    persistence = root / "skeleton" / "persistence"
    scanned: list[str] = []
    for name in FILES:
        path = persistence / name
        if not path.is_file():
            raise MotorBootstrapControlError(f"missing bootstrap module: {name}")
        scanned.append(name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imports: list[str] = []
            if isinstance(node, ast.Import):
                imports = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module.split(".")[0]]
            if any(name in {"motor", "pymongo"} for name in imports):
                raise MotorBootstrapControlError(
                    f"live Mongo driver import found in {path.name}"
                )
    return scanned


def verify_mirror_parity(root: Path) -> list[str]:
    canonical = root / "skeleton" / "persistence"
    mirror = root / "skeleton" / "ai" / "runtime" / "persistence"
    verified: list[str] = []
    for name in FILES:
        left = canonical / name
        right = mirror / name
        if not left.is_file() or not right.is_file():
            raise MotorBootstrapControlError(f"missing mirrored bootstrap module: {name}")
        if left.read_bytes() != right.read_bytes():
            raise MotorBootstrapControlError(f"Motor bootstrap mirror drift: {name}")
        verified.append(name)
    return verified


def build_report(root: Path) -> dict[str, object]:
    root = root.resolve()
    scanned = verify_no_driver_imports(root)
    mirrored = verify_mirror_parity(root)
    plan = SpineMotorPlan().card()
    if plan["count"] != 3:
        raise MotorBootstrapControlError("canonical bootstrap plan must contain three indexes")
    if plan["live_motor"] is not False or plan["driver_imported"] is not False:
        raise MotorBootstrapControlError("bootstrap plan gained live driver authority")
    if len(plan["digest"]) != 64:
        raise MotorBootstrapControlError("bootstrap plan digest is invalid")
    collections = [row["collection"] for row in plan["indexes"]]
    if collections != ["receipts", "watermarks", "fence"]:
        raise MotorBootstrapControlError("bootstrap collection order changed")
    return {
        "schema_version": 1,
        "control": "p2-motor-bootstrap-v1",
        "valid": True,
        "modules": scanned,
        "mirror_count": len(mirrored),
        "plan_digest": plan["digest"],
        "index_count": plan["count"],
        "live_motor": False,
        "driver_imported": False,
        "activated": False,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        report = build_report(root)
    except (OSError, SyntaxError, ValueError, MotorBootstrapControlError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "control": "p2-motor-bootstrap-v1",
                    "valid": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
