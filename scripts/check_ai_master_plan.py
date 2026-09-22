#!/usr/bin/env python3
"""Validate the canonical Skeleton AI master plan/index.

Dependency-free and intentionally fail-closed: malformed or incomplete volume
coverage is an architecture error.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "machine" / "ai_master_plan.json"
INDEX = ROOT / "docs" / "plan" / "MASTER_INDEX.md"
PLAN = ROOT / "docs" / "plan" / "MASTER_PLAN.md"
DEPTH_000_040 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_000_040.md"

EXPECTED_FIRST = 0
EXPECTED_LAST = 420
EXPECTED_COUNT = EXPECTED_LAST - EXPECTED_FIRST + 1


class PlanValidationError(RuntimeError):
    pass


def load_plan() -> dict:
    if not MACHINE.is_file():
        raise PlanValidationError(f"missing machine plan: {MACHINE.relative_to(ROOT)}")
    try:
        data = json.loads(MACHINE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanValidationError(f"cannot parse machine plan: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanValidationError("machine plan root must be an object")
    return data


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    engineering = data.get("engineering_pass")
    if not isinstance(engineering, dict):
        errors.append("engineering_pass must be an object")
    else:
        if engineering.get("machine_contract") != "machine/ai_engineering_pass.json":
            errors.append("engineering_pass machine contract path drifted")
        if engineering.get("human_contract") != "docs/plan/ENGINEERING_PASS.md":
            errors.append("engineering_pass human contract path drifted")
        required_promotions = engineering.get("required_for_promotion")
        if required_promotions != ["verified", "hardened", "production"]:
            errors.append("engineering_pass required_for_promotion must be verified/hardened/production")
    freeze = data.get("breadth_freeze")
    if not isinstance(freeze, dict) or freeze.get("enabled") is not True:
        errors.append("breadth_freeze.enabled must be true")
    elif freeze.get("last_top_level_volume") != EXPECTED_LAST:
        errors.append(f"breadth_freeze.last_top_level_volume must be {EXPECTED_LAST}")

    maturity = data.get("volume_maturity_policy")
    if not isinstance(maturity, dict):
        errors.append("volume_maturity_policy must be an object")
        maturity = {}

    volumes = data.get("volumes")
    if not isinstance(volumes, list):
        errors.append("volumes must be a list")
        return errors
    if len(volumes) != EXPECTED_COUNT:
        errors.append(f"expected {EXPECTED_COUNT} volumes, found {len(volumes)}")

    ids = [v.get("id") for v in volumes if isinstance(v, dict)]
    expected = list(range(EXPECTED_FIRST, EXPECTED_LAST + 1))
    if ids != expected:
        errors.append("volume ids must be unique, ordered, and contiguous from 0 through 420")

    keys = [v.get("key") for v in volumes if isinstance(v, dict)]
    if len(set(keys)) != len(keys):
        errors.append("volume keys must be unique")

    for volume in volumes:
        if not isinstance(volume, dict):
            errors.append("every volume must be an object")
            continue
        for field in ("id", "key", "title", "status", "documentation", "implementation_status"):
            if field not in volume:
                errors.append(f"volume {volume.get('id', '?')} missing {field}")
        status = volume.get("status")
        if status not in {"specified", "scaffolded", "implemented", "integrated", "verified", "hardened", "production", "experimental", "deprecated", "retired"}:
            errors.append(f"volume {volume.get('id', '?')} has invalid status")
        policy = maturity.get(status, {}) if isinstance(maturity, dict) else {}
        required = policy.get("required_nonempty_fields", []) if isinstance(policy, dict) else []
        if not isinstance(required, list):
            errors.append(f"volume maturity policy {status!r} has invalid required_nonempty_fields")
            required = []
        for required_field in required:
            value = volume.get(required_field)
            if not isinstance(value, list) or not value:
                errors.append(
                    f"volume {volume.get('id', '?')} status {status} requires non-empty {required_field}"
                )

    for path in (INDEX, PLAN, DEPTH_000_040):
        if not path.is_file():
            errors.append(f"missing document: {path.relative_to(ROOT)}")

    if INDEX.is_file():
        text = INDEX.read_text(encoding="utf-8")
        if "Volume 420" not in text and "| 420 |" not in text:
            errors.append("master index does not expose Volume 420")
        if "Breadth status: **FROZEN" not in text:
            errors.append("master index must declare breadth freeze")

    depth_passes = data.get("depth_passes")
    if not isinstance(depth_passes, list):
        errors.append("depth_passes must be a list")
    else:
        dp = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-000-040"), None)
        if not isinstance(dp, dict):
            errors.append("missing DP-000-040 depth pass")
        else:
            if dp.get("volume_range") != [0, 40]:
                errors.append("DP-000-040 volume_range must equal [0, 40]")
            fields = dp.get("required_nonempty_fields")
            if not isinstance(fields, list) or not fields:
                errors.append("DP-000-040 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[:41]:
                    if volume.get("depth_pass") != "DP-000-040":
                        errors.append(f"{volume.get('key', '?')}: missing DP-000-040 marker")
                    for field in fields:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

    if DEPTH_000_040.is_file():
        depth_text = DEPTH_000_040.read_text(encoding="utf-8")
        for marker in ("DP-000-040", "VOL-000", "VOL-040", "Remaining work after DP-000-040"):
            if marker not in depth_text:
                errors.append(f"volume depth doc missing marker: {marker}")

    if PLAN.is_file():
        text = PLAN.read_text(encoding="utf-8")
        for marker in ("## 21. P0 build program", "## 21.5 Systems-engineering closure overlay", "## 22. Vertical-slice acceptance ladder", "## 24.2 Volume maturity promotion contract", "## 24.3 Volume depth passes", "## 25. Scope freeze"):
            if marker not in text:
                errors.append(f"master plan missing required section: {marker}")

    return errors


def main() -> int:
    try:
        data = load_plan()
    except PlanValidationError as exc:
        print(f"AI master plan: FAIL: {exc}")
        return 1
    errors = validate(data)
    if errors:
        print("AI master plan: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    print(f"AI master plan: OK ({EXPECTED_COUNT} volumes, breadth frozen at {EXPECTED_LAST})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
