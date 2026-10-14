from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_priority_queue_mirrors_signed_accountability_ledger() -> None:
    ledger = _load("machine/ai_build_accountability.json")
    priority = _load("machine/ai_edge_case_priority_queue.json")

    records = {
        record["id"]: record
        for record in ledger["records"]
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }

    assert priority["items"], "priority queue must not be empty"

    for item in priority["items"]:
        record = records[item["accountability_id"]]
        assert item["signing_required"] is True
        assert item["status"] == record["status"]
        assert item["accountability_status"] == record["status"]
        assert item["completion_checkbox"] == record["checkbox"]
        assert item["completion_checkbox_mark"] == record["checkbox_mark"]
