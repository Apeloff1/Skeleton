#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "machine/masterplan_overlay_reconciliation.json"

def _read(path: str) -> bytes:
    p = ROOT / path
    if not p.is_file():
        raise AssertionError(f"missing required authority: {path}")
    data = p.read_bytes()
    if len(data) < 2:
        raise AssertionError(f"empty/truncated required authority: {path} ({len(data)} bytes)")
    return data

def _json(path: str) -> Any:
    data = _read(path)
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise AssertionError(f"invalid JSON authority: {path}: {exc}") from exc

def _semver(value: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if not m:
        raise AssertionError(f"invalid semantic version: {value!r}")
    return tuple(map(int, m.groups()))

def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def validate() -> dict[str, Any]:
    contract = _json("machine/masterplan_overlay_reconciliation.json")
    errors: list[str] = []

    for path in contract["required_json_authorities"]:
        try:
            _json(path)
        except AssertionError as exc:
            errors.append(str(exc))

    for path in contract["required_human_authorities"]:
        try:
            _read(path)
        except AssertionError as exc:
            errors.append(str(exc))

    plan = _json("machine/ai_master_plan.json")
    version = str(plan.get("plan_version", ""))
    try:
        if _semver(version) < _semver(contract["minimum_plan_version"]):
            errors.append(
                f"plan_version regressed: {version} < {contract['minimum_plan_version']}"
            )
    except AssertionError as exc:
        errors.append(str(exc))

    for key in contract["required_machine_plan_keys"]:
        if key not in plan:
            errors.append(f"machine plan missing cumulative overlay key: {key}")

    parse_index = _json(contract["parse_index"])
    sources = parse_index.get("sources", {})
    for path in contract["canonical_sources"]:
        expected = ((sources.get(path) or {}).get("git_blob_sha"))
        if not expected:
            errors.append(f"parse index missing source identity: {path}")
            continue
        actual = _git_blob_sha(_read(path))
        if actual != expected:
            errors.append(
                f"parse index stale for {path}: expected {expected}, actual {actual}"
            )

    master_plan = _read("docs/plan/MASTER_PLAN.md").decode("utf-8", errors="replace")
    master_index = _read("docs/plan/MASTER_INDEX.md").decode("utf-8", errors="replace")
    required_markers = [
        "FRONTIER_96_AI_LADDER",
        "ADVANCED_AI_100_LEVELS",
        "CS_300_COMPUTER_SCIENCE_LADDER",
        "LEARNING_400_ADVERSARIAL_400",
        "PROJECT_SELF_IMPROVEMENT_1000",
        "ESSENTIALS_1000",
        "COMPETITIVE_AI_ENGINEERING_LADDER",
        "AI_GAME_BUILDER_500_LEVELS",
    ]
    for marker in required_markers:
        if marker not in master_plan and marker not in master_index:
            errors.append(f"human canonical plan/index lost overlay marker: {marker}")

    result = {
        "ok": not errors,
        "plan_version": version,
        "required_json_authorities": len(contract["required_json_authorities"]),
        "required_human_authorities": len(contract["required_human_authorities"]),
        "errors": errors,
    }
    if errors:
        raise AssertionError("\n".join(errors))
    return result

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = validate()
    except AssertionError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"FAIL: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"OK masterplan overlay reconciliation: plan={result['plan_version']} "
            f"json={result['required_json_authorities']} human={result['required_human_authorities']}"
        )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
