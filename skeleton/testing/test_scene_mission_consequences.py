"""Canonical mission consequence attribution, alternate endings and forgery."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_mission import (
    demo_actions, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_consequences import (
    SceneTravelError, cli, compare_consequences, export_comparison,
    import_comparison, inspect_consequences, original_alternative,
)


def original_path():
    return simulate_mission(original_mission(), demo_actions())


def test_original_mission_attribution_and_earned_ending() -> None:
    report = inspect_consequences(original_path())
    assert report["ending"] == "lantern_restored"
    assert report["reputation"] == 6
    assert report["turns"] == 5
    assert report["history"][0]["choice_resolved"] == {
        "choice_id": "restore_lantern", "option_id": "help"
    }
    assert report["history"][0]["missions_earned"] == ["pledge"]
    assert report["history"][0]["reputation_delta"] == 3
    assert report["history"][-1]["ending"] == "lantern_restored"
    assert report["receipt"] == dig({k: v for k, v in report.items() if k != "receipt"})


def test_alternate_choice_changes_missions_reputation_and_ending() -> None:
    a, b = original_path(), original_alternative()
    report = compare_consequences(a, b)
    assert report["relationship"] == "divergent"
    assert report["common_turns"] == 0
    assert report["choice_differences"] == [
        {"choice_id": "restore_lantern", "left": "help", "right": "decline"}
    ]
    assert report["left"]["ending"] == "lantern_restored"
    assert report["right"]["ending"] == "unpledged_victory"
    assert "pledge" in report["missions_only_left"]
    assert report["reputation_delta_right_minus_left"] < 0


def test_same_and_prefix_mission_relationships() -> None:
    full = original_path()
    prefix = simulate_mission(original_mission(), demo_actions()[:2])
    assert compare_consequences(full, full)["relationship"] == "identical"
    result = compare_consequences(prefix, full)
    assert result["relationship"] == "prefix"
    assert result["common_turns"] == 2


def test_export_import_replays_both_alternate_histories() -> None:
    bundle = export_comparison(original_path(), original_alternative())
    assert import_comparison(json.loads(json.dumps(bundle))) == bundle["report"]
    bad = copy.deepcopy(bundle)
    bad["report"]["left"]["reputation"] += 999
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay mismatch"):
        import_comparison(bad)


def test_source_mismatch_and_tampered_saves_fail_closed() -> None:
    a = original_path()
    changed = original_mission()
    changed["director_id"] = "other_director"
    b = simulate_mission(changed, demo_actions())
    with pytest.raises(SceneTravelError, match="identical authored source"):
        compare_consequences(a, b)
    forged = copy.deepcopy(a)
    forged["state"]["reputation"] = 999
    with pytest.raises(SceneTravelError):
        inspect_consequences(forged)


def test_cli_demo_and_portable_import(capsys) -> None:
    assert cli(["demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["relationship"] == "divergent"
    bundle = export_comparison(original_path(), original_alternative())
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == bundle["report"]


def test_cli_rejects_invalid_json(capsys) -> None:
    assert cli(["inspect", "--session-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
