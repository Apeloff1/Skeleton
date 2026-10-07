from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EDGE_QUEUE = REPO_ROOT / "machine" / "ai_edge_case_priority_queue.json"
BACKLOG = REPO_ROOT / "machine" / "backlog_registry.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_backlog_mirrors_every_edge_case_status() -> None:
    edge = _load(EDGE_QUEUE)
    backlog = _load(BACKLOG)

    expected = {item["id"]: item["status"] for item in edge["items"]}
    mirrored = {
        item["source_ref"]: item["status"]
        for item in backlog["items"]
        if item.get("source_type") == "edge_case"
    }

    assert set(mirrored) == set(expected)
    assert mirrored == expected


def test_edge_case_backlog_ids_are_canonical() -> None:
    edge = _load(EDGE_QUEUE)
    backlog = _load(BACKLOG)

    actual = {
        item["source_ref"]: item["id"]
        for item in backlog["items"]
        if item.get("source_type") == "edge_case"
    }
    expected = {item["id"]: f"BL-EDGE-{item['id']}" for item in edge["items"]}

    assert actual == expected
