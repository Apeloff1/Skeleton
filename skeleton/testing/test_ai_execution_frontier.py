from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_execution_frontier_validator_passes() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_ai_execution_frontier.py")],
        cwd=ROOT,
        check=True,
    )


def test_execution_frontier_tracks_landed_stage3_without_promoting_ledger() -> None:
    frontier = json.loads(
        (ROOT / "machine" / "ai_execution_frontier_20260924.json").read_text(
            encoding="utf-8"
        )
    )
    assert frontier["landed_candidate_summary"]["through_stage"] == 3
    assert frontier["landed_candidate_summary"]["task_count"] >= 22
    assert any(
        candidate["task_id"] == "AIQ-S1-MEM-03"
        and candidate["landed_commits"]
        == ["a2cb66b9847ff893d750aafbf6ba61d3f1a8eba0"]
        for candidate in frontier["promotion_candidates"]
    )
    assert frontier["queue_snapshot"] == {
        "done": 1,
        "evidence_pending": 6,
        "in_progress": 1,
        "pending": 34,
        "total": 42,
    }
