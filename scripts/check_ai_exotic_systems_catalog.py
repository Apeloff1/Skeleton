#!/usr/bin/env python3
"""Validate the breadth-frozen exotic systems depth catalogue."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "machine" / "ai_exotic_systems_catalog.json"
HUMAN = ROOT / "docs" / "plan" / "EXOTIC_SYSTEMS_DEPTH.md"
MASTER = ROOT / "machine" / "ai_master_plan.json"

VALID_RISK = {"low", "medium", "high", "reference"}
VALID_TIERS = {"watchlist", "research_sandbox", "shadow", "canary", "production"}

def validate() -> list[str]:
    errors: list[str] = []
    if not CATALOG.is_file():
        return ["missing machine/ai_exotic_systems_catalog.json"]
    if not HUMAN.is_file():
        errors.append("missing docs/plan/EXOTIC_SYSTEMS_DEPTH.md")
    if not MASTER.is_file():
        return errors + ["missing machine/ai_master_plan.json"]

    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    valid_volumes = {v["id"] for v in master["volumes"]}
    valid_wps = set(master.get("p0_work_packages", []))
    entries = data.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]

    ids = [e.get("id") for e in entries if isinstance(e, dict)]
    if len(ids) != len(set(ids)):
        errors.append("exotic entry ids must be unique")

    cats = Counter()
    mapped_wps: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("every exotic entry must be an object")
            continue
        eid = entry.get("id", "?")
        for field in ("category", "title", "mechanism", "status", "activation_tier", "kill_switch", "fallback"):
            if not str(entry.get(field, "")).strip():
                errors.append(f"{eid}: missing {field}")
        cats[str(entry.get("category", ""))] += 1
        if entry.get("risk_level") not in VALID_RISK:
            errors.append(f"{eid}: invalid risk_level")
        if entry.get("activation_tier") not in VALID_TIERS:
            errors.append(f"{eid}: invalid activation_tier")
        if entry.get("production_authority") is not False:
            errors.append(f"{eid}: production_authority must default false")
        mapped = entry.get("mapped_volumes")
        if not isinstance(mapped, list) or not mapped:
            errors.append(f"{eid}: mapped_volumes must be non-empty")
        elif any(v not in valid_volumes for v in mapped):
            errors.append(f"{eid}: references unknown volume")
        refs = entry.get("work_package_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{eid}: work_package_refs must be non-empty")
        elif set(refs) - valid_wps:
            errors.append(f"{eid}: references unknown work package")
        else:
            mapped_wps.update(refs)
        for field in ("prerequisites", "required_evidence"):
            value = entry.get(field)
            if not isinstance(value, list) or len(value) < 2 or any(not str(x).strip() for x in value):
                errors.append(f"{eid}: {field} must contain at least two non-empty items")

    mins = data.get("required_minimums", {})
    if len(entries) < mins.get("total", 0):
        errors.append(f"expected at least {mins.get('total')} entries, found {len(entries)}")
    if len(cats) < mins.get("categories", 0):
        errors.append(f"expected at least {mins.get('categories')} categories, found {len(cats)}")
    if len(mapped_wps) < mins.get("mapped_work_packages", 0):
        errors.append(
            f"expected at least {mins.get('mapped_work_packages')} mapped work packages, found {len(mapped_wps)}"
        )
    if set(data.get("categories", [])) != set(cats):
        errors.append("declared categories must exactly match entry categories")
    if data.get("breadth_freeze_compatible") is not True:
        errors.append("catalog must declare breadth_freeze_compatible=true")
    if data.get("policy", {}).get("production_authority_default") is not False:
        errors.append("policy.production_authority_default must be false")
    return errors

def main() -> int:
    errors = validate()
    if errors:
        print("AI exotic systems catalogue: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = Counter(e["category"] for e in data["entries"])
    print(
        "AI exotic systems catalogue: OK "
        f"({len(data['entries'])} entries across {len(categories)} categories)"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
