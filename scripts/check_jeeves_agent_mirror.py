#!/usr/bin/env python3
"""Prevent the two installed Jeeves agent paths from silently diverging.

This checks the actual implementation bytes, not an exported feature list.
A canonical/mirror mismatch is a build defect: one runtime may be running
old release, memory, verifier, or scheduler logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path("skeleton/jeeves/agent")
MIRROR = Path("skeleton/ai/agents/jeeves/agent")
REQUIRED = (
    "adaptive_runtime.py",
    "adversarial_verifier_review.py",
    "code_delivery_quality.py",
    "code_scrutiny_loop.py",
    "delivery_assurance_milestones.py",
    "delivery_evidence_journal.py",
    "delivery_milestone_queue.py",
    "delivery_milestone_workbench.py",
    "delivery_milestones.py",
    "final_delivery_reviews.py",
    "runtime.py",
    "working_context_cycle.py",
)


def check_parity(root: Path = ROOT) -> dict[str, object]:
    """Rebuild equality evidence from immutable checked-out files."""
    records = []
    for name in REQUIRED:
        original = root / CANONICAL / name
        mirror = root / MIRROR / name
        if not original.is_file() or not mirror.is_file():
            records.append({"name": name, "status": "missing"})
            continue
        left = original.read_bytes()
        right = mirror.read_bytes()
        canonical_hash = hashlib.sha256(left).hexdigest()
        mirror_hash = hashlib.sha256(right).hexdigest()
        records.append({
            "name": name,
            "status": "matched" if left == right else "drifted",
            "canonical_sha256": canonical_hash,
            "mirror_sha256": mirror_hash,
            "canonical_bytes": len(left),
            "mirror_bytes": len(right),
        })
    return {
        "schema": "skeleton.jeeves.agent.mirror_parity.v1",
        "scope": "required code-delivery and milestone integration",
        "status": "passed" if all(
            item["status"] == "matched" for item in records
        ) and len(records) == len(REQUIRED) else "blocked",
        "checked": len(records),
        "files": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed on diverged Jeeves agent mirrors")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_parity()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["files"]:
            if item["status"] != "matched":
                print(f"{item['status']}: {item['name']}")
        print(f"jeeves agent mirror parity: {report['status']} ({report['checked']} files)")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
