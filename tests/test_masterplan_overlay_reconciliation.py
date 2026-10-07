from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_cumulative_overlay_reconciliation_validator_passes():
    proc = subprocess.run(
        [sys.executable, "scripts/check_masterplan_overlay_reconciliation.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["ok"] is True
    assert result["plan_version"] == "2.6.0"
    assert result["overlay_count"] == 8


def test_restored_overlay_cardinalities_and_no_false_completion():
    advanced = load("machine/advanced_ai_structure_100.json")
    frontier = load("machine/frontier_96_ai_ladder.json")
    cs = load("machine/cs_300_computer_science_ladder.json")
    learning = load("machine/learning_400_adversarial_400.json")
    psi = load("machine/project_self_improvement_1000.json")
    ess = load("machine/essentials_1000.json")
    competitive = load("machine/competitive_ai_engineering_ladder.json")
    game = load("machine/ai_game_builder_500_levels.json")

    assert len(advanced["levels"]) == 100
    assert advanced["completion"]["implementation_claim"] is False
    assert advanced["completion"]["signed_levels"] == []

    assert len(frontier["layers"]) == 96
    assert frontier["completion"]["signed_complete"] == 0
    assert frontier["completion"]["frontier_96_qualified"] is False

    assert len(cs["layers"]) == 300
    assert cs["completion"]["signed_complete"] == 0
    assert cs["completion"]["cs_300_qualified"] is False

    assert len(learning["learning_layers"]) == 400
    assert len(learning["adversarial_layers"]) == 400
    assert learning["completion"]["learning_signed_complete"] == 0
    assert learning["completion"]["adversarial_signed_complete"] == 0

    assert len(psi["levels"]) == 1000
    assert psi["completion"]["template_signed_complete"] == 0
    assert psi["completion"]["implementation_claim"] is False

    assert len(ess["levels"]) == 1000
    assert ess["completion"]["signed_complete"] == 0
    assert ess["completion"]["implementation_claim"] is False

    assert len(competitive["levels"]) == 200
    assert all(level["status"] == "planned" for level in competitive["levels"])
    assert all(level["signed"] is False for level in competitive["levels"])

    rows = []
    for shard in game["shards"]:
        rows.extend(load(shard)["levels"])
    assert len(rows) == 500
    assert rows[0]["id"] == "GBL-001"
    assert rows[-1]["id"] == "GBL-500"
    assert all(row["signed"] is False for row in rows)


def test_masterplan_union_preserves_all_overlay_authorities():
    plan = load("machine/ai_master_plan.json")
    expected = [
        "advanced-ai-100",
        "frontier-96",
        "cs-300",
        "learning-400-adversarial-400",
        "psi-1000",
        "ess-1000",
        "competitive-200",
        "game-builder-500",
    ]
    assert [o["id"] for o in plan["frontier_overlay_stack"]["overlays"]] == expected
    assert plan["canonical_overlay_reconciliation"]["fail_closed"] is True
    assert plan["breadth_freeze"]["last_top_level_volume"] == 420
