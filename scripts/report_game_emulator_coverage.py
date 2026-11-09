"""Operator-only emulation readiness matrix: recipe != installed != qualified.

Never download, compile, load or launch a core. This reporter only reads
canonical Dragon hardware targets, pinned build recipes and (optionally)
the approved registry's existing validated catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.install_game_emulator_cores import PINNED_CORES
from skeleton.jeeves.game_emulator_catalog import (
    EmulatorCatalogError,
    GameEmulatorRegistry,
    canonical_targets,
)


def coverage_report(registry_path: str | None = None) -> dict[str, object]:
    targets = canonical_targets()
    build_candidates: dict[str, list[str]] = {target: [] for target in targets}
    for core_id, recipe in sorted(PINNED_CORES.items()):
        for target in recipe["targets"]:
            if target in build_candidates:
                build_candidates[target].append(core_id)
    approved: dict[str, dict] = {}
    if registry_path is not None:
        registry = GameEmulatorRegistry(registry_path)
        approved = {row["target_id"]: row for row in registry.catalog()}
        if set(approved) != set(targets):
            raise ValueError("Operator registry target catalog is out of sync")
    rows = []
    for target_id in sorted(targets):
        result = approved.get(target_id)
        installed = None if result is None else bool(result["available"])
        rows.append({
            "target_id": target_id,
            "family": targets[target_id].get("family"),
            "build_core_ids": build_candidates[target_id],
            "build_recipe_available": bool(build_candidates[target_id]),
            "registry_checked": result is not None,
            "approved_core_available": installed,
            "approved_core_id": (
                result["core"]["core_id"]
                if result is not None and result["core"] is not None else None
            ),
            "readiness_code": (
                result["readiness"]["code"] if result is not None
                else "registry_not_checked"
            ),
            "core_boot_verified": False,
            "controller_verified": False,
            "hardware_accuracy_verified": False,
            "training_qualified": False,
        })
    counts = Counter()
    for row in rows:
        counts["targets"] += 1
        counts["with_pinned_source_recipe"] += bool(row["build_recipe_available"])
        counts["missing_build_recipe"] += not row["build_recipe_available"]
        if row["registry_checked"]:
            counts["registry_evaluated"] += 1
            counts["approved_installed"] += row["approved_core_available"] is True
            counts["not_approved_or_unavailable"] += row["approved_core_available"] is False
    payload = {
        "schema_version": "skeleton.game.emulator_coverage.v1",
        "registry_checked": registry_path is not None,
        "pinned_core_recipe_count": len(PINNED_CORES),
        "summary": dict(counts),
        "rows": rows,
        "limitations": (
            "Build recipe is not compiled binary; approved installed core is not "
            "successful ROM boot, controller certification, hardware accuracy or "
            "AI training qualification. No ROM, core or model was executed."
        ),
    }
    payload["report_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", help="Private operator-approved registry for exact installed/readiness checks")
    parser.add_argument("--summary", action="store_true", help="Print aggregate statistics instead of per-target JSON")
    args = parser.parse_args(argv)
    try:
        report = coverage_report(args.registry)
    except (EmulatorCatalogError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc)[:256]}), file=sys.stderr)
        return 2
    if args.summary:
        print(json.dumps({
            "schema_version": report["schema_version"],
            "registry_checked": report["registry_checked"],
            "pinned_core_recipe_count": report["pinned_core_recipe_count"],
            "summary": report["summary"],
            "report_sha256": report["report_sha256"],
        }, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
