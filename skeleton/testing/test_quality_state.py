"""Quality state persistence tests."""
from __future__ import annotations

from skeleton.organism.quality_state import append_quality, latest_quality, load_quality, quality_snapshot


def test_quality_state_appends_and_reads(tmp_path):
    append_quality({"surface": "plan", "accepted": True, "reason": "accepted", "score": 0.9, "weakest_path": "grounding"}, root=tmp_path)
    append_quality({"surface": "npc", "accepted": False, "reason": "low_score", "score": 0.3, "weakest_path": "behavior"}, root=tmp_path)
    rows = load_quality(root=tmp_path)
    assert len(rows) == 2
    assert latest_quality(root=tmp_path)["surface"] == "npc"
    snap = quality_snapshot(root=tmp_path)
    assert snap["rollup"]["count"] == 2
    assert snap["rollup"]["rejected"] == 1
