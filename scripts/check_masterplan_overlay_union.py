#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "machine/masterplan_overlay_registry.json"
MASTER = ROOT / "machine/ai_master_plan.json"
INDEX = ROOT / "machine/ai_masterplan_parse_index.json"
ACCOUNTABILITY = ROOT / "machine/ai_build_accountability.json"
MASTER_MD = ROOT / "docs/plan/MASTER_PLAN.md"
MASTER_INDEX = ROOT / "docs/plan/MASTER_INDEX.md"

def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))

def git_blob(path: Path) -> str:
    return subprocess.check_output(["git","hash-object",str(path)], cwd=ROOT, text=True).strip()

def validate() -> list[str]:
    errors: list[str] = []
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    floor = version_tuple(registry["canonical_plan_version_floor"])
    actual = version_tuple(master["plan_version"])
    if actual < floor:
        errors.append(f"plan_version regressed: {master['plan_version']} < {registry['canonical_plan_version_floor']}")
    md = MASTER_MD.read_text(encoding="utf-8")
    mi = MASTER_INDEX.read_text(encoding="utf-8")
    for overlay in registry["overlays"]:
        for key in ("authority","human","validator","test"):
            p = ROOT / overlay[key]
            if not p.exists():
                errors.append(f"{overlay['id']}: missing {overlay[key]}")
        wf = overlay.get("workflow")
        if wf and not (ROOT / wf).exists():
            errors.append(f"{overlay['id']}: missing {wf}")
        authority = ROOT / overlay["authority"]
        if authority.exists():
            size = authority.stat().st_size
            if size < int(overlay["minimum_bytes"]):
                errors.append(f"{overlay['id']}: authority too small {size} < {overlay['minimum_bytes']}")
            else:
                try:
                    json.loads(authority.read_text(encoding="utf-8"))
                except Exception as exc:
                    errors.append(f"{overlay['id']}: invalid JSON: {exc}")
        marker = overlay["authority"]
        if marker not in md:
            errors.append(f"{overlay['id']}: MASTER_PLAN missing {marker}")
        if marker not in mi:
            errors.append(f"{overlay['id']}: MASTER_INDEX missing {marker}")
    for rel in registry["secondary_authorities"]:
        p = ROOT / rel
        if not p.exists() or p.stat().st_size == 0:
            errors.append(f"secondary authority missing/empty: {rel}")
        else:
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"secondary authority invalid JSON {rel}: {exc}")
    sources = index["sources"]
    expected_master = sources["machine/ai_master_plan.json"]["git_blob_sha"]
    actual_master = git_blob(MASTER)
    if expected_master != actual_master:
        errors.append(f"parse-index master SHA stale: {expected_master} != {actual_master}")
    expected_acc = sources["machine/ai_build_accountability.json"]["git_blob_sha"]
    actual_acc = git_blob(ACCOUNTABILITY)
    if expected_acc != actual_acc:
        errors.append(f"parse-index accountability SHA stale: {expected_acc} != {actual_acc}")
    if len(master.get("volumes", [])) != 421:
        errors.append(f"master volume count drifted: {len(master.get('volumes', []))} != 421")
    required_keys = {
        "frontier_96","advanced_ai_structure_100","cs_300",
        "learning_400_adversarial_400","project_self_improvement_1000",
        "essentials_1000","competitive_engineering_ladder","ai_game_builder_500_levels"
    }
    missing = sorted(required_keys - set(master))
    if missing:
        errors.append("master missing overlay summaries: " + ", ".join(missing))
    return errors

def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("masterplan overlay union valid: 8/8 overlays, 421 volumes, exact source identities")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
