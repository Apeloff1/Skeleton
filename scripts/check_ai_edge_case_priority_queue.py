#!/usr/bin/env python3
"""Validate the prioritized P0/P1 AI edge-case queue."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "machine" / "ai_edge_case_priority_queue.json"
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"

ALLOWED_STATUSES = {
    "planned",
    "in_progress",
    "evidence_pending",
    "passing",
    "accepted_risk",
    "closed",
}
PRIORITY_BY_CRITICALITY = {
    "critical": "P0",
    "high": "P1",
}


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain an object")
    return data


def _string_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def validate(
    queue: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        if queue is None:
            if not QUEUE.is_file():
                return ["machine/ai_edge_case_priority_queue.json is missing"]
            queue = _load(QUEUE)
        if catalog is None:
            if not CATALOG.is_file():
                return ["machine/ai_edge_case_catalog.json is missing"]
            catalog = _load(CATALOG)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse AI edge priority inputs: {exc}"]

    if queue.get("schema_version") != 1:
        errors.append("priority queue schema_version must equal 1")
    if queue.get("status") != "active":
        errors.append("priority queue status must remain active")
    if queue.get("source_catalog") != "machine/ai_edge_case_catalog.json":
        errors.append("priority queue source_catalog path drifted")
    if queue.get("source_matrix") != "machine/ai_full_edge_case_matrix.json":
        errors.append("priority queue source_matrix path drifted")
    if set(queue.get("status_values") or []) != ALLOWED_STATUSES:
        errors.append("priority queue status_values drifted")

    items = queue.get("items")
    entries = catalog.get("entries")
    if not isinstance(items, list):
        return errors + ["priority queue items must be a list"]
    if not isinstance(entries, list):
        return errors + ["edge-case catalog entries must be a list"]

    expected_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("criticality") in PRIORITY_BY_CRITICALITY
    ]
    expected_ids = {entry.get("id") for entry in expected_entries}
    catalog_by_id = {
        entry.get("id"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    ids = [
        item.get("id")
        for item in items
        if isinstance(item, dict)
    ]
    if len(ids) != len(items) or any(not isinstance(item_id, str) or not item_id for item_id in ids):
        errors.append("every priority queue item requires a non-empty id")
    if len(ids) != len(set(ids)):
        errors.append("priority queue item ids must be unique")
    if set(ids) != expected_ids:
        errors.append(
            "priority queue must contain every critical/high catalog entry exactly once"
        )

    ranks = [
        item.get("rank")
        for item in items
        if isinstance(item, dict)
    ]
    if ranks != list(range(1, len(items) + 1)):
        errors.append("priority queue ranks must be contiguous and ordered from 1")

    counts = queue.get("counts")
    actual_counts = Counter(
        item.get("priority")
        for item in items
        if isinstance(item, dict)
    )
    if not isinstance(counts, dict):
        errors.append("priority queue counts must be an object")
    else:
        if counts.get("total") != len(items):
            errors.append("priority queue counts.total is stale")
        for priority in ("P0", "P1"):
            if counts.get(priority) != actual_counts[priority]:
                errors.append(f"priority queue counts.{priority} is stale")

    for item in items:
        if not isinstance(item, dict):
            errors.append("every priority queue item must be an object")
            continue
        item_id = str(item.get("id") or "?")
        source = catalog_by_id.get(item_id)
        if source is None:
            errors.append(f"{item_id}: priority item missing source catalog entry")
            continue

        criticality = item.get("criticality")
        expected_priority = PRIORITY_BY_CRITICALITY.get(criticality)
        if expected_priority is None:
            errors.append(f"{item_id}: only critical/high entries may be prioritized")
        elif item.get("priority") != expected_priority:
            errors.append(
                f"{item_id}: priority must be {expected_priority} for {criticality}"
            )

        for field in ("criticality", "title", "domain", "accountability_id"):
            if item.get(field) != source.get(field):
                errors.append(f"{item_id}: {field} drifted from source catalog")
        for field in ("work_package_refs", "recommended_test_modes"):
            if item.get(field) != source.get(field):
                errors.append(f"{item_id}: {field} drifted from source catalog")

        if item.get("status") not in ALLOWED_STATUSES:
            errors.append(f"{item_id}: invalid priority status")
        evidence = item.get("evidence")
        if not _string_list(evidence, allow_empty=True):
            errors.append(f"{item_id}: evidence must be a string list")
            evidence = []
        disposition = item.get("disposition")
        accepted_risk = item.get("accepted_risk")

        if item.get("status") == "planned":
            if evidence:
                errors.append(f"{item_id}: planned item cannot claim evidence")
            if disposition not in (None, ""):
                errors.append(f"{item_id}: planned item cannot claim disposition")
            if accepted_risk is not None:
                errors.append(f"{item_id}: planned item cannot claim accepted_risk")
        elif item.get("status") == "evidence_pending":
            if not evidence:
                errors.append(f"{item_id}: evidence_pending item needs evidence refs")
            if not isinstance(disposition, str) or not disposition.strip():
                errors.append(f"{item_id}: evidence_pending item needs disposition")
            if accepted_risk is not None:
                errors.append(f"{item_id}: evidence_pending item cannot claim accepted_risk")
        elif item.get("status") in {"passing", "closed"}:
            if not evidence:
                errors.append(f"{item_id}: {item.get('status')} item needs evidence refs")
            if not isinstance(disposition, str) or not disposition.strip():
                errors.append(f"{item_id}: {item.get('status')} item needs disposition")
            if accepted_risk is not None:
                errors.append(f"{item_id}: passing/closed item cannot claim accepted_risk")
        elif item.get("status") == "accepted_risk":
            if not isinstance(accepted_risk, dict) or not accepted_risk:
                errors.append(f"{item_id}: accepted_risk status needs risk record")

        expected_accountability = f"ACC-{item_id}"
        if item.get("accountability_id") != expected_accountability:
            errors.append(
                f"{item_id}: accountability_id must equal {expected_accountability}"
            )
        if item.get("signing_required") is not True:
            errors.append(f"{item_id}: signing_required must be true")
        checkbox = item.get("completion_checkbox")
        if checkbox not in (True, False):
            errors.append(f"{item_id}: completion_checkbox must be boolean")
        else:
            expected_mark = "[x]" if checkbox else "[ ]"
            if item.get("completion_checkbox_mark") != expected_mark:
                errors.append(
                    f"{item_id}: completion_checkbox_mark disagrees with checkbox"
                )
        if not isinstance(item.get("accountability_status"), str) or not item["accountability_status"].strip():
            errors.append(f"{item_id}: accountability_status must be non-empty")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AI edge-case priority queue: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    queue = _load(QUEUE)
    print(
        "AI edge-case priority queue: OK "
        f"({len(queue['items'])} items; "
        f"{queue['counts']['P0']} P0, {queue['counts']['P1']} P1)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
