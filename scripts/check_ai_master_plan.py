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
DEPTH_041_080 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_041_080.md"
DEPTH_081_120 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_081_120.md"
DEPTH_121_160 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_121_160.md"
DEPTH_161_200 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_161_200.md"
DEPTH_201_240 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_201_240.md"
DEPTH_241_280 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_241_280.md"
DEPTH_281_320 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_281_320.md"
DEPTH_321_360 = ROOT / "docs" / "plan" / "VOLUME_DEPTH_321_360.md"

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
        if engineering.get("task_matrix") != "machine/ai_engineering_task_matrix.json":
            errors.append("engineering_pass task_matrix must equal machine/ai_engineering_task_matrix.json")
        if engineering.get("task_matrix_human") != "docs/plan/ENGINEERING_TASK_MATRIX.md":
            errors.append("engineering_pass task_matrix_human path drifted")
    adversarial = data.get("adversarial_closure")
    if not isinstance(adversarial, dict):
        errors.append("adversarial_closure must be an object")
    else:
        if adversarial.get("machine_contract") != "machine/ai_adversarial_closure.json":
            errors.append("adversarial_closure machine contract path drifted")
        if adversarial.get("human_contract") != "docs/plan/ADVERSARIAL_CLOSURE_PASS.md":
            errors.append("adversarial_closure human contract path drifted")
        if adversarial.get("required_for_promotion") != ["verified", "hardened", "production"]:
            errors.append("adversarial_closure required_for_promotion must be verified/hardened/production")

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

    for path in (INDEX, PLAN, DEPTH_000_040, DEPTH_041_080, DEPTH_081_120, DEPTH_121_160, DEPTH_161_200, DEPTH_201_240, DEPTH_241_280, DEPTH_281_320, DEPTH_321_360):
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

        dp2 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-041-080"), None)
        if not isinstance(dp2, dict):
            errors.append("missing DP-041-080 depth pass")
        else:
            if dp2.get("volume_range") != [41, 80]:
                errors.append("DP-041-080 volume_range must equal [41, 80]")
            fields2 = dp2.get("required_nonempty_fields")
            if not isinstance(fields2, list) or not fields2:
                errors.append("DP-041-080 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[41:81]:
                    if volume.get("depth_pass") != "DP-041-080":
                        errors.append(f"{volume.get('key', '?')}: missing DP-041-080 marker")
                    for field in fields2:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp3 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-081-120"), None)
        if not isinstance(dp3, dict):
            errors.append("missing DP-081-120 depth pass")
        else:
            if dp3.get("volume_range") != [81, 120]:
                errors.append("DP-081-120 volume_range must equal [81, 120]")
            fields3 = dp3.get("required_nonempty_fields")
            if not isinstance(fields3, list) or not fields3:
                errors.append("DP-081-120 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[81:121]:
                    if volume.get("depth_pass") != "DP-081-120":
                        errors.append(f"{volume.get('key', '?')}: missing DP-081-120 marker")
                    for field in fields3:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp4 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-121-160"), None)
        if not isinstance(dp4, dict):
            errors.append("missing DP-121-160 depth pass")
        else:
            if dp4.get("volume_range") != [121, 160]:
                errors.append("DP-121-160 volume_range must equal [121, 160]")
            fields4 = dp4.get("required_nonempty_fields")
            if not isinstance(fields4, list) or not fields4:
                errors.append("DP-121-160 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[121:161]:
                    if volume.get("depth_pass") != "DP-121-160":
                        errors.append(f"{volume.get('key', '?')}: missing DP-121-160 marker")
                    for field in fields4:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp5 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-161-200"), None)
        if not isinstance(dp5, dict):
            errors.append("missing DP-161-200 depth pass")
        else:
            if dp5.get("volume_range") != [161, 200]:
                errors.append("DP-161-200 volume_range must equal [161, 200]")
            fields5 = dp5.get("required_nonempty_fields")
            if not isinstance(fields5, list) or not fields5:
                errors.append("DP-161-200 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[161:201]:
                    if volume.get("depth_pass") != "DP-161-200":
                        errors.append(f"{volume.get('key', '?')}: missing DP-161-200 marker")
                    for field in fields5:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp6 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-201-240"), None)
        if not isinstance(dp6, dict):
            errors.append("missing DP-201-240 depth pass")
        else:
            if dp6.get("volume_range") != [201, 240]:
                errors.append("DP-201-240 volume_range must equal [201, 240]")
            fields6 = dp6.get("required_nonempty_fields")
            if not isinstance(fields6, list) or not fields6:
                errors.append("DP-201-240 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[201:241]:
                    if volume.get("depth_pass") != "DP-201-240":
                        errors.append(f"{volume.get('key', '?')}: missing DP-201-240 marker")
                    for field in fields6:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp7 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-241-280"), None)
        if not isinstance(dp7, dict):
            errors.append("missing DP-241-280 depth pass")
        else:
            if dp7.get("volume_range") != [241, 280]:
                errors.append("DP-241-280 volume_range must equal [241, 280]")
            fields7 = dp7.get("required_nonempty_fields")
            if not isinstance(fields7, list) or not fields7:
                errors.append("DP-241-280 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[241:281]:
                    if volume.get("depth_pass") != "DP-241-280":
                        errors.append(f"{volume.get('key', '?')}: missing DP-241-280 marker")
                    for field in fields7:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp8 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-281-320"), None)
        if not isinstance(dp8, dict):
            errors.append("missing DP-281-320 depth pass")
        else:
            if dp8.get("volume_range") != [281, 320]:
                errors.append("DP-281-320 volume_range must equal [281, 320]")
            fields8 = dp8.get("required_nonempty_fields")
            if not isinstance(fields8, list) or not fields8:
                errors.append("DP-281-320 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[281:321]:
                    if volume.get("depth_pass") != "DP-281-320":
                        errors.append(f"{volume.get('key', '?')}: missing DP-281-320 marker")
                    for field in fields8:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

        dp9 = next((x for x in depth_passes if isinstance(x, dict) and x.get("id") == "DP-321-360"), None)
        if not isinstance(dp9, dict):
            errors.append("missing DP-321-360 depth pass")
        else:
            if dp9.get("volume_range") != [321, 360]:
                errors.append("DP-321-360 volume_range must equal [321, 360]")
            fields9 = dp9.get("required_nonempty_fields")
            if not isinstance(fields9, list) or not fields9:
                errors.append("DP-321-360 required_nonempty_fields must be non-empty")
            else:
                for volume in volumes[321:361]:
                    if volume.get("depth_pass") != "DP-321-360":
                        errors.append(f"{volume.get('key', '?')}: missing DP-321-360 marker")
                    for field in fields9:
                        value = volume.get(field)
                        if not isinstance(value, list) or not value:
                            errors.append(f"{volume.get('key', '?')}: depth pass requires non-empty {field}")

    if DEPTH_000_040.is_file():
        depth_text = DEPTH_000_040.read_text(encoding="utf-8")
        for marker in ("DP-000-040", "VOL-000", "VOL-040", "Remaining work after DP-000-040"):
            if marker not in depth_text:
                errors.append(f"volume depth doc missing marker: {marker}")

    if DEPTH_041_080.is_file():
        depth_text = DEPTH_041_080.read_text(encoding="utf-8")
        for marker in ("DP-041-080", "VOL-041", "VOL-080", "Remaining work after DP-041-080"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_081_120.is_file():
        depth_text = DEPTH_081_120.read_text(encoding="utf-8")
        for marker in ("DP-081-120", "VOL-081", "VOL-120", "Remaining work after DP-081-120"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_121_160.is_file():
        depth_text = DEPTH_121_160.read_text(encoding="utf-8")
        for marker in ("DP-121-160", "VOL-121", "VOL-160", "Remaining work after DP-121-160"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_161_200.is_file():
        depth_text = DEPTH_161_200.read_text(encoding="utf-8")
        for marker in ("DP-161-200", "VOL-161", "VOL-200", "Remaining work after DP-161-200"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_201_240.is_file():
        depth_text = DEPTH_201_240.read_text(encoding="utf-8")
        for marker in ("DP-201-240", "VOL-201", "VOL-240", "Remaining work after DP-201-240"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_241_280.is_file():
        depth_text = DEPTH_241_280.read_text(encoding="utf-8")
        for marker in ("DP-241-280", "VOL-241", "VOL-280", "Remaining work after DP-241-280"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_281_320.is_file():
        depth_text = DEPTH_281_320.read_text(encoding="utf-8")
        for marker in ("DP-281-320", "VOL-281", "VOL-320", "Remaining work after DP-281-320"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if DEPTH_321_360.is_file():
        depth_text = DEPTH_321_360.read_text(encoding="utf-8")
        for marker in ("DP-321-360", "VOL-321", "VOL-360", "Remaining work after DP-321-360"):
            if marker not in depth_text:
                errors.append(f"sequential volume depth doc missing marker: {marker}")

    if PLAN.is_file():
        text = PLAN.read_text(encoding="utf-8")
        for marker in ("## 21. P0 build program", "## 21.5 Systems-engineering closure overlay", "## 21.6 Atomic task engineering propagation", "## 21.6 Adversarial cross-condition closure overlay", "## 22. Vertical-slice acceptance ladder", "## 24.2 Volume maturity promotion contract", "## 24.3 Volume depth passes", "## 25. Scope freeze"):
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
