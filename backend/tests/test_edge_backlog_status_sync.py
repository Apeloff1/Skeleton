from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EDGE_QUEUE = REPO_ROOT / "machine" / "ai_edge_case_priority_queue.json"
BACKLOG = REPO_ROOT / "machine" / "backlog_registry.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_backlog_preserves_edge_case_lifecycle_without_false_closure() -> None:
    edge = _load(EDGE_QUEUE)
    backlog = _load(BACKLOG)

    sources = {item["id"]: item for item in edge["items"]}
    mirrored = {
        item["source_ref"]: item
        for item in backlog["items"]
        if item.get("source_type") == "edge_case"
    }

    assert set(mirrored) == set(sources)
    for source_ref, source in sources.items():
        row = mirrored[source_ref]
        assert row["id"] == f"BL-EDGE-{source_ref}"
        assert row["priority_class"] == source["priority"]
        assert row["rationale"] == source["title"]
        assert "machine/ai_edge_case_priority_queue.json" in row["provenance"]
        assert (
            "status must be passing, accepted_risk or closed"
            in row["closure_rule"]
        )

        # The edge queue owns source maturity. The deduplicated backlog owns
        # work lifecycle and may advance to evidence_pending once concrete
        # evidence exists, but it must not infer passing/closure from that.
        assert source["status"] == "planned"
        if source["evidence"]:
            assert row["status"] == "evidence_pending"
        else:
            assert row["status"] == "planned"
        assert row["status"] not in {
            "passing",
            "accepted_risk",
            "closed",
            "landed_unpromoted",
        }


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
