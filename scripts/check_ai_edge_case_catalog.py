#!/usr/bin/env python3
"""Validate Skeleton's edge-case, obscure-pattern and historical catalogue."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"
HUMAN = ROOT / "docs" / "plan" / "EDGE_CASES_HISTORICAL.md"
MASTER = ROOT / "machine" / "ai_master_plan.json"

VALID_TYPES = {"historical", "edge_case", "obscure_pattern"}


def validate() -> list[str]:
    errors: list[str] = []
    if not CATALOG.is_file():
        return ["missing machine/ai_edge_case_catalog.json"]
    if not HUMAN.is_file():
        errors.append("missing docs/plan/EDGE_CASES_HISTORICAL.md")
    if not MASTER.is_file():
        errors.append("missing machine/ai_master_plan.json")
        return errors

    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    volume_ids = {v["id"] for v in master["volumes"]}
    entries = data.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]

    ids = [e.get("id") for e in entries if isinstance(e, dict)]
    if len(ids) != len(set(ids)):
        errors.append("catalog entry ids must be unique")

    counts = Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("every entry must be an object")
            continue
        entry_id = entry.get("id", "?")
        typ = entry.get("type")
        if typ not in VALID_TYPES:
            errors.append(f"{entry_id}: invalid type {typ!r}")
            continue
        counts[typ] += 1
        for field in ("title", "domain", "lesson", "status"):
            if not str(entry.get(field, "")).strip():
                errors.append(f"{entry_id}: missing {field}")
        mapped = entry.get("mapped_volumes")
        if not isinstance(mapped, list) or not mapped:
            errors.append(f"{entry_id}: mapped_volumes must be non-empty")
        elif any(v not in volume_ids for v in mapped):
            errors.append(f"{entry_id}: references unknown volume")

    mins = data.get("required_minimums", {})
    for typ in VALID_TYPES:
        required = mins.get(typ)
        if not isinstance(required, int) or required < 1:
            errors.append(f"required_minimums.{typ} must be positive integer")
        elif counts[typ] < required:
            errors.append(f"{typ}: expected at least {required}, found {counts[typ]}")
    total = mins.get("total")
    if not isinstance(total, int) or len(entries) < total:
        errors.append(f"expected at least {total} total entries, found {len(entries)}")

    if data.get("breadth_freeze_compatible") is not True:
        errors.append("catalog must declare breadth_freeze_compatible=true")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AI edge/historical catalogue: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    counts = Counter(e["type"] for e in data["entries"])
    print(
        "AI edge/historical catalogue: OK "
        f"({len(data['entries'])} entries; "
        f"{counts['historical']} historical, "
        f"{counts['edge_case']} edge, "
        f"{counts['obscure_pattern']} obscure)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
