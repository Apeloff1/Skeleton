"""Quest journal reward timeline and deterministic save comparison."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.game.gameplay.quest_session import (
    GameplayContractError, QuestEngine, QuestPlan, QuestTrigger,
)
from skeleton.game.gameplay.quest_timeline import (
    SCHEMA, compare_journals, inspect_journal,
    verify_comparison, verify_timeline,
)


def _fixtures():
    root = Path(__file__).resolve().parents[2] / "docs/game/fixtures"
    plan = json.loads((root / "lantern_harbor_quests.json").read_text(encoding="utf-8"))
    actions = json.loads((root / "lantern_harbor_events.json").read_text(encoding="utf-8"))
    return QuestEngine(QuestPlan.from_record(plan)), [
        QuestTrigger(**event) for event in actions
    ]


def test_real_rewards_and_ending_in_timeline() -> None:
    engine, events = _fixtures()
    save = engine.replay(events).save_record()
    report = inspect_journal(engine, save)
    assert report["schema_version"] == SCHEMA
    assert report["event_count"] == 2
    assert report["timeline"][0]["item_deltas"] == {"map": 1}
    assert report["timeline"][0]["currency_delta"] == 5
    assert report["timeline"][1]["item_deltas"] == {"star": 2}
    assert report["timeline"][1]["currency_delta"] == 9
    assert report["ending_id"] == "safe_harbor"
    assert report["currency"] == 14
    assert verify_timeline(engine, json.loads(json.dumps(save)), report) == report


def test_save_prefix_comparison_and_replay() -> None:
    engine, events = _fixtures()
    left = engine.replay(events[:1]).save_record()
    right = engine.replay(events).save_record()
    report = compare_journals(engine, left, right)
    assert report["relationship"] == "prefix"
    assert report["common_events"] == 1
    assert report["right"]["ending_id"] == "safe_harbor"
    assert verify_comparison(engine, left, right, report) == report


def test_identical_saves_are_identical() -> None:
    engine, events = _fixtures()
    save = engine.replay(events).save_record()
    result = compare_journals(engine, save, copy.deepcopy(save))
    assert result["relationship"] == "identical"
    assert result["first_divergent_event"] is None


def test_forged_rewards_fail_before_inspection() -> None:
    engine, events = _fixtures()
    save = engine.replay(events).save_record()
    save["state"]["currency"] = 999
    with pytest.raises(GameplayContractError):
        inspect_journal(engine, save)


def test_modified_timeline_receipt_rejected() -> None:
    engine, events = _fixtures()
    save = engine.replay(events).save_record()
    report = inspect_journal(engine, save)
    report["timeline"][0]["currency_delta"] = 999
    with pytest.raises(GameplayContractError, match="receipt"):
        verify_timeline(engine, save, report)


def test_changed_source_rejects_old_save() -> None:
    engine, events = _fixtures()
    save = engine.replay(events).save_record()
    other, _ = _fixtures()
    other.plan.quests[0].reward  # stable original source, not mutable
    plan = engine.plan.as_record()
    plan["world_id"] = "other_harbor"
    with pytest.raises(GameplayContractError):
        inspect_journal(QuestEngine(QuestPlan.from_record(plan)), save)


def test_cli_timeline_over_real_save(tmp_path: Path) -> None:
    engine, events = _fixtures()
    save_path = tmp_path / "quest-save.json"
    save_path.write_text(json.dumps(engine.replay(events).save_record()), encoding="utf-8")
    plan_path = Path(__file__).resolve().parents[2] / "docs/game/fixtures/lantern_harbor_quests.json"
    run = subprocess.run([
        sys.executable, "-m", "skeleton.game.gameplay.quest_cli",
        "timeline", "--plan", str(plan_path), "--save", str(save_path),
    ], capture_output=True, text=True, check=False, timeout=15)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["ending_id"] == "safe_harbor"
    assert verify_timeline(engine, engine.replay(events).save_record(), report) == report
