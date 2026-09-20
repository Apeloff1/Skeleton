#!/usr/bin/env python3
"""Validate machine-repository integrity while surfacing organization debt."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.repo_machine.builder import RepositoryModelBuilder
from skeleton.repo_machine.debt import debt_register
from skeleton.repo_machine.health import repository_health
from skeleton.repo_machine.planner import candidate_payload
from skeleton.repo_machine.selfcheck import run_selfcheck


def main() -> int:
    try:
        builder = RepositoryModelBuilder(ROOT)
        model = builder.build()
        health = repository_health(model)
        work = candidate_payload(model, limit=20)
        selfcheck = run_selfcheck(model, builder.config)
        debt = debt_register(model, limit=20)
    except Exception as exc:
        print(
            f"repository machine contract failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    summary = {
        "fingerprint": model.fingerprint,
        "files": len(model.files),
        "subsystems": len(model.subsystems),
        "edges": len(model.edges),
        "cycles": len(model.cycles),
        "findings": len(model.findings),
        "unclassified": model.unclassified_count,
        "truncated": model.truncated,
        "health": health.as_dict(),
        "work_candidates": len(work["work"]),
        "debt_sample": len(debt),
        "selfcheck": [item.as_dict() for item in selfcheck],
    }
    print(json.dumps(summary, sort_keys=True))

    hard_failures = [
        item
        for item in selfcheck
        if item.severity in {"critical", "high"}
    ]
    if model.truncated:
        print(
            "repository machine contract failed: inventory truncated",
            file=sys.stderr,
        )
        return 1
    critical_scan = [
        item
        for item in model.findings
        if item.severity == "critical"
        and item.code.startswith("scan.")
    ]
    if critical_scan:
        print(
            "repository machine contract failed: critical scanner findings",
            file=sys.stderr,
        )
        return 1
    if hard_failures:
        print(
            "repository machine contract failed: "
            + "; ".join(
                f"{item.code}: {item.detail}"
                for item in hard_failures
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
