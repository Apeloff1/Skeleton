#!/usr/bin/env python3
"""Fail-closed validation for cumulative Skeleton masterplan overlay authority."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "machine/ai_master_plan.json"
PARSE_INDEX = ROOT / "machine/ai_masterplan_parse_index.json"
ACCOUNTABILITY = ROOT / "machine/ai_build_accountability.json"

REQUIRED = {
    "advanced-ai-100": (
        "machine/advanced_ai_structure_100.json",
        "docs/plan/ADVANCED_AI_100_LEVELS.md",
        "scripts/check_advanced_ai_structure.py",
        "tests/test_advanced_ai_structure.py",
        ".github/workflows/advanced-ai-structure.yml",
    ),
    "frontier-96": (
        "machine/frontier_96_ai_ladder.json",
        "docs/plan/FRONTIER_96_AI_LADDER.md",
        "scripts/check_frontier_96_ladder.py",
        "tests/test_frontier_96_ladder.py",
    ),
    "cs-300": (
        "machine/cs_300_computer_science_ladder.json",
        "docs/plan/CS_300_COMPUTER_SCIENCE_LADDER.md",
        "scripts/check_cs_300_ladder.py",
        "tests/test_cs_300_ladder.py",
        ".github/workflows/cs-300-authority.yml",
    ),
    "learning-400-adversarial-400": (
        "machine/learning_400_adversarial_400.json",
        "docs/plan/LEARNING_400_ADVERSARIAL_400.md",
        "scripts/check_learning_400_adversarial_400.py",
        "tests/test_learning_400_adversarial_400.py",
        ".github/workflows/learning-400-adversarial-400.yml",
    ),
    "psi-1000": (
        "machine/project_self_improvement_1000.json",
        "docs/plan/PROJECT_SELF_IMPROVEMENT_1000.md",
        "scripts/check_project_self_improvement_1000.py",
        "tests/test_project_self_improvement_1000.py",
        ".github/workflows/project-self-improvement-1000.yml",
    ),
    "ess-1000": (
        "machine/essentials_1000.json",
        "docs/plan/ESSENTIALS_1000.md",
        "scripts/check_essentials_1000.py",
        "tests/test_essentials_1000.py",
        ".github/workflows/essentials-1000.yml",
    ),
    "competitive-200": (
        "machine/competitive_ai_engineering_ladder.json",
        "machine/competitive_ai_benchmark_governance.json",
        "docs/architecture/COMPETITIVE_AI_ENGINEERING_LADDER.md",
        "docs/architecture/COMPETITIVE_AI_BENCHMARK_GOVERNANCE.md",
        "scripts/check_competitive_ai_engineering_ladder.py",
        "tests/test_competitive_ai_engineering_ladder.py",
    ),
    "game-builder-500": (
        "machine/ai_game_builder_500_levels.json",
        "machine/ai_game_builder_dual_rival_forge.json",
        "docs/architecture/AI_GAME_BUILDER_500_LEVELS.md",
        "scripts/check_ai_game_builder_500_levels.py",
        "tests/test_ai_game_builder_500_levels.py",
        ".github/workflows/ai-game-builder-500-levels.yml",
    ),
}

JSON_AUTHORITIES = (
    "machine/advanced_ai_structure_100.json",
    "machine/advanced_ai_maturity_ledger.json",
    "machine/frontier_96_ai_ladder.json",
    "machine/cs_300_computer_science_ladder.json",
    "machine/learning_400_adversarial_400.json",
    "machine/project_self_improvement_1000.json",
    "machine/essentials_1000.json",
    "machine/competitive_ai_engineering_ladder.json",
    "machine/competitive_ai_benchmark_governance.json",
    "machine/ai_game_builder_500_levels.json",
    "machine/ai_game_builder_dual_rival_forge.json",
    "machine/ai_build_accountability.json",
)

AUTHORITY_BINDINGS = {
    "advanced_ai_structure_100": "machine/advanced_ai_structure_100.json",
    "advanced_ai_maturity_ledger": "machine/advanced_ai_maturity_ledger.json",
    "frontier_96_ladder": "machine/frontier_96_ai_ladder.json",
    "cs_300_ladder": "machine/cs_300_computer_science_ladder.json",
    "learning_400_adversarial_400": "machine/learning_400_adversarial_400.json",
    "project_self_improvement_1000": "machine/project_self_improvement_1000.json",
    "essentials_1000": "machine/essentials_1000.json",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


def version_tuple(value: str) -> tuple[int, int, int]:
    try:
        parts = tuple(int(p) for p in value.split("."))
    except ValueError as exc:
        raise AssertionError(f"invalid plan_version: {value!r}") from exc
    if len(parts) != 3:
        fail(f"plan_version must be x.y.z, got {value!r}")
    return parts


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if version_tuple(plan["plan_version"]) < (2, 5, 0):
        fail(f"masterplan regressed below 2.5.0: {plan['plan_version']}")

    stack = plan.get("frontier_overlay_stack") or {}
    overlays = stack.get("overlays") or []
    ids = [item.get("id") for item in overlays]
    expected = list(REQUIRED)
    if ids != expected:
        fail(f"overlay stack mismatch: expected {expected}, got {ids}")
    if len(ids) != len(set(ids)):
        fail("duplicate overlay IDs in canonical stack")

    reconciliation = plan.get("canonical_overlay_reconciliation") or {}
    if reconciliation.get("fail_closed") is not True:
        fail("canonical overlay reconciliation must fail closed")

    authority = plan.get("authority") or {}
    for key, expected_path in AUTHORITY_BINDINGS.items():
        if authority.get(key) != expected_path:
            fail(f"authority binding {key!r} is {authority.get(key)!r}, expected {expected_path!r}")

    for overlay_id, paths in REQUIRED.items():
        for rel in paths:
            path = ROOT / rel
            if not path.is_file():
                fail(f"{overlay_id}: missing required file {rel}")
            if path.stat().st_size == 0:
                fail(f"{overlay_id}: empty required file {rel}")

    for rel in JSON_AUTHORITIES:
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"missing or empty JSON authority: {rel}")
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"invalid JSON authority {rel}: {exc}")

    if not PARSE_INDEX.is_file() or PARSE_INDEX.stat().st_size == 0:
        fail("parse index missing or empty")
    parse_index = json.loads(PARSE_INDEX.read_text(encoding="utf-8"))
    sources = parse_index.get("sources") or {}
    plan_source = (sources.get("machine/ai_master_plan.json") or {}).get("git_blob_sha")
    acc_source = (sources.get("machine/ai_build_accountability.json") or {}).get("git_blob_sha")
    actual_plan = git_blob_sha(PLAN)
    actual_acc = git_blob_sha(ACCOUNTABILITY)
    if plan_source != actual_plan:
        fail(f"stale parse-index masterplan SHA: {plan_source} != {actual_plan}")
    if acc_source != actual_acc:
        fail(f"stale parse-index accountability SHA: {acc_source} != {actual_acc}")

    master_plan_md = (ROOT / "docs/plan/MASTER_PLAN.md").read_text(encoding="utf-8")
    master_index_md = (ROOT / "docs/plan/MASTER_INDEX.md").read_text(encoding="utf-8")
    for token in (
        "Advanced AI 100-level authority",
        "Frontier-96",
        "CS-300",
        "Learning-400",
        "PSI-1000",
        "ESS-1000",
        "Competitive",
        "Game Builder",
    ):
        if token not in master_plan_md and token not in master_index_md:
            fail(f"canonical human authority lost overlay marker: {token}")

    expected_human_version = f"Plan version: **{plan['plan_version']}**"
    if expected_human_version not in master_plan_md:
        fail(
            "human masterplan version does not match machine authority: "
            f"{plan['plan_version']}"
        )

    result = {
        "ok": True,
        "plan_version": plan["plan_version"],
        "overlay_count": len(ids),
        "overlays": ids,
        "masterplan_blob": actual_plan,
        "accountability_blob": actual_acc,
        "json_authorities": len(JSON_AUTHORITIES),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
