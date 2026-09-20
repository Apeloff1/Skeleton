#!/usr/bin/env python3
"""Validate the machine repository contract without treating existing debt as a hard failure."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.repo_machine.builder import build_repository_model
from skeleton.repo_machine.health import repository_health
from skeleton.repo_machine.planner import candidate_payload


def main() -> int:
    try:
        model = build_repository_model(ROOT)
        health = repository_health(model)
        work = candidate_payload(model, limit=20)
    except Exception as exc:
        print(f"repository machine contract failed: {type(exc).__name__}: {exc}", file=sys.stderr)
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
    }
    print(json.dumps(summary, sort_keys=True))

    if model.truncated:
        print("repository machine contract failed: inventory truncated", file=sys.stderr)
        return 1
    critical_scan = [item for item in model.findings if item.severity == "critical" and item.code.startswith("scan.")]
    if critical_scan:
        print("repository machine contract failed: critical scanner findings", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
