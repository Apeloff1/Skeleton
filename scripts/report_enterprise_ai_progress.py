#!/usr/bin/env python3
"""Report enterprise-AI completion separately from legacy implementation state."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from check_enterprise_ai_superiority import validate
from check_enterprise_ai_implementation_notes import validate as validate_notes


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "machine" / "enterprise_ai_superiority.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"

GRADE_ORDER = {
    "designed": 0,
    "implemented": 1,
    "hardened": 2,
    "enterprise_qualified": 3,
    "superior": 4,
}


def build_report(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    validation = validate(root)
    notes_validation = validate_notes(root)
    policy = json.loads(
        (root / "machine" / "enterprise_ai_superiority.json").read_text(
            encoding="utf-8"
        )
    )
    master = json.loads(
        (root / "machine" / "ai_master_plan.json").read_text(encoding="utf-8")
    )

    volumes = master["volumes"]
    grade_counts = Counter(row["enterprise_grade_state"] for row in volumes)
    target_counts = Counter(row["enterprise_grade_target"] for row in volumes)
    legacy_counts = Counter(row["implementation_status"] for row in volumes)
    dedicated = set(policy["coverage"]["dedicated_profiles_required_for"])

    qualified = sum(
        GRADE_ORDER[row["enterprise_grade_state"]]
        >= GRADE_ORDER["enterprise_qualified"]
        for row in volumes
    )
    critical_superior = sum(
        row["key"] in dedicated and row["enterprise_grade_state"] == "superior"
        for row in volumes
    )
    all_graded = sum(
        row["enterprise_grade_state"] in GRADE_ORDER for row in volumes
    )

    total = len(volumes)
    critical_total = len(dedicated)
    complete = qualified == total and critical_superior == critical_total

    return {
        "status": "complete" if complete else "in_progress",
        "policy_version": policy["version"],
        "master_plan_version": master["plan_version"],
        "volume_count": total,
        "dedicated_superiority_profile_count": critical_total,
        "golden_journey_count": validation["golden_journey_count"],
        "implementation_dossier_count": notes_validation["dossier_count"],
        "implementation_dossier_coverage_percent": round(
            100.0
            * notes_validation["dossier_count"]
            / notes_validation["volume_count"],
            2,
        ),
        "implementation_levels_per_volume": notes_validation["required_level_count"],
        "implementation_notebook_count": notes_validation["depth_pass_count"],
        "design_coverage_percent": round(100.0 * all_graded / total, 2),
        "enterprise_qualified_volume_count": qualified,
        "enterprise_qualification_percent": round(100.0 * qualified / total, 2),
        "critical_superior_volume_count": critical_superior,
        "critical_superiority_percent": round(
            100.0 * critical_superior / critical_total,
            2,
        ),
        "enterprise_grade_counts": dict(sorted(grade_counts.items())),
        "enterprise_target_counts": dict(sorted(target_counts.items())),
        "legacy_implementation_counts": dict(sorted(legacy_counts.items())),
        "complete_enterprise_ai_claim": complete,
        "next_gate": (
            "qualify all volumes and prove dedicated comparator superiority"
            if not complete
            else "maintain evidence freshness on every governed source/policy change"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_report(Path(args.root))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
