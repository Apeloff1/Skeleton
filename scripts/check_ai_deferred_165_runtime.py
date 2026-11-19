#!/usr/bin/env python3
"""Fail-closed validator for the deferred 165-volume AI execution map."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.ai.runtime.deferred.catalog import DEFERRED_165_SPECS


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    frontier = _load(ROOT / "machine/ai_masterplan_continuation_frontier.json")
    master = _load(ROOT / "machine/ai_master_plan.json")
    execution = _load(ROOT / "machine/ai_deferred_165_execution_map.json")

    expected = frontier["next_tranche"]["queued_volume_refs"]
    if len(expected) != 165:
        _fail(errors, f"canonical frontier expected 165 queued volumes, got {len(expected)}")
    if len(expected) != len(set(expected)):
        _fail(errors, "canonical frontier contains duplicate queued volume ids")

    rows = execution.get("volumes")
    if not isinstance(rows, list):
        _fail(errors, "execution map volumes must be a list")
        rows = []

    ids = [
        row.get("volume_id")
        for row in rows
        if isinstance(row, dict)
    ]
    if len(rows) != 165:
        _fail(errors, f"execution map must contain 165 rows, got {len(rows)}")
    if len(ids) != len(set(ids)):
        _fail(errors, "execution map contains duplicate volume ids")
    if set(ids) != set(expected):
        _fail(
            errors,
            "execution map volume set differs from canonical frontier "
            f"missing={sorted(set(expected)-set(ids))} "
            f"extra={sorted(set(ids)-set(expected))}",
        )

    if execution.get("expected_volume_count") != 165:
        _fail(errors, "expected_volume_count must be 165")
    if execution.get("completion_authority") is not False:
        _fail(errors, "execution map must not grant completion authority")
    if execution.get("implementation_status") != "branch_candidate":
        _fail(errors, "execution map must remain branch_candidate before landing/evidence")

    master_by_key = {
        volume["key"]: volume
        for volume in master.get("volumes", [])
        if isinstance(volume, dict) and isinstance(volume.get("key"), str)
    }
    catalog = {spec.volume_id: spec for spec in DEFERRED_165_SPECS}
    if set(catalog) != set(expected):
        _fail(errors, "Python catalog does not exactly match canonical 165-volume set")

    for row in rows:
        if not isinstance(row, dict):
            _fail(errors, "execution map row must be object")
            continue
        volume_id = row.get("volume_id")
        source = master_by_key.get(volume_id)
        if source is None:
            _fail(errors, f"{volume_id}: missing from masterplan")
            continue
        if row.get("title") != source.get("title"):
            _fail(errors, f"{volume_id}: title drift")
        if row.get("source_gaps") != source.get("gaps"):
            _fail(errors, f"{volume_id}: gap inventory drift")
        if row.get("source_risks") != source.get("risks"):
            _fail(errors, f"{volume_id}: risk inventory drift")
        if row.get("completion_claim") is not False:
            _fail(errors, f"{volume_id}: completion_claim must remain false")
        if row.get("promotion_authority") is not False:
            _fail(errors, f"{volume_id}: promotion_authority must remain false")
        if row.get("implementation_state") != "branch_candidate":
            _fail(errors, f"{volume_id}: implementation_state must be branch_candidate")

        handler = row.get("handler")
        if not isinstance(handler, str) or "." not in handler:
            _fail(errors, f"{volume_id}: handler must be importable dotted path")
            continue
        module_name, attribute = handler.rsplit(".", 1)
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            _fail(errors, f"{volume_id}: handler module import failed: {exc}")
            continue
        if not hasattr(module, attribute):
            _fail(errors, f"{volume_id}: handler attribute missing: {handler}")

        spec = catalog.get(volume_id)
        if spec is None:
            continue
        if spec.title != row.get("title"):
            _fail(errors, f"{volume_id}: Python catalog title drift")
        if spec.plane != row.get("plane"):
            _fail(errors, f"{volume_id}: Python catalog plane drift")
        if spec.handler != handler:
            _fail(errors, f"{volume_id}: Python catalog handler drift")
        if list(spec.risks) != row.get("source_risks"):
            _fail(errors, f"{volume_id}: Python catalog risks drift")

    if errors:
        print("AI deferred-165 validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    plane_counts: dict[str, int] = {}
    for row in rows:
        plane = row["plane"]
        plane_counts[plane] = plane_counts.get(plane, 0) + 1
    print(
        "AI deferred-165 validation passed: "
        f"{len(rows)} volumes; planes={dict(sorted(plane_counts.items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
