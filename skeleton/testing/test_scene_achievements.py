"""Replay-derived achievements: legitimate milestones, forgery and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_achievements import (
    SceneTravelError, cli, export_achievements, import_achievements,
    inspect_achievements, normalize_rules, original_catalog,
)
from skeleton.game.gameplay.scene_travel import (
    new_session, original_demo, resume_session, simulate,
)


def test_original_milestones_are_earned_from_replayed_actions() -> None:
    world, actions = original_demo()
    catalog = original_catalog(world)
    report = inspect_achievements(simulate(world, actions), catalog)
    earned = {x["id"]: x for x in report["achievements"] if x["earned"]}
    assert set(earned) == {"first_steps", "key_keeper", "safe_arrival", "swift_arrival"}
    assert earned["first_steps"]["witness"]["tick"] == 0
    assert earned["first_steps"]["witness"]["action_receipt"] is None
    assert earned["key_keeper"]["witness"]["tick"] == 1
    assert earned["safe_arrival"]["witness"]["tick"] == 3
    assert report["earned_count"] == 4


def test_partial_checkpoint_resume_matches_complete_replay() -> None:
    world, actions = original_demo()
    catalog = original_catalog(world)
    partial = simulate(world, actions[:1])
    assert inspect_achievements(partial, catalog)["earned_count"] == 2
    resumed = resume_session(json.loads(json.dumps(partial)), actions[1:])
    assert inspect_achievements(resumed, catalog) == inspect_achievements(
        simulate(world, actions), catalog
    )


def test_failure_ending_does_not_award_victory() -> None:
    world, _ = original_demo()
    result = simulate(world, [{"kind": "travel", "exit_id": "down"}])
    report = inspect_achievements(result, original_catalog(world))
    earned = {r["id"] for r in report["achievements"] if r["earned"]}
    assert earned == {"first_steps", "sinkhole_warning", "swift_arrival"}


def test_portable_bundle_replays_and_detects_tampering() -> None:
    world, actions = original_demo()
    bundle = export_achievements(simulate(world, actions), original_catalog(world))
    assert import_achievements(json.loads(json.dumps(bundle))) == bundle["report"]
    bad = copy.deepcopy(bundle)
    bad["report"]["earned_count"] = 99
    with pytest.raises(SceneTravelError, match="checksum"):
        import_achievements(bad)
    bad = copy.deepcopy(bundle)
    bad["session"]["state"]["scene_id"] = "sinkhole"
    bad["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError, match="checksum"):
        import_achievements(bad)


def test_recomputed_checksum_cannot_forge_a_replay_reward() -> None:
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    world, actions = original_demo()
    bundle = export_achievements(simulate(world, actions), original_catalog(world))
    forged = copy.deepcopy(bundle)
    forged["report"]["earned_count"] = 5
    forged["checksum"] = dig({k: v for k, v in forged.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay"):
        import_achievements(forged)


@pytest.mark.parametrize("change", [
    lambda c: c["rules"].append(c["rules"][0]),
    lambda c: c["rules"][0].update(id=c["rules"][1]["id"]),
    lambda c: c["rules"][0].update(target="unknown_scene"),
    lambda c: c["rules"][1].update(target="unknown_item"),
    lambda c: c["rules"][2].update(target="win"),
    lambda c: c["rules"][3].update(target=True),
    lambda c: c["rules"][3].update(target=MAX_VALUE),
    lambda c: c.update(source_digest="0" * 64),
    lambda c: c.update(unsafe="extra"),
])
def test_invalid_catalog_fails_closed(change) -> None:
    world, _ = original_demo()
    session = new_session(world)
    catalog = original_catalog(world)
    change(catalog)
    with pytest.raises(SceneTravelError):
        normalize_rules(catalog, session["world"], session["source_digest"])


MAX_VALUE = 513


def test_cli_demo_and_import(capsys) -> None:
    assert cli(["demo"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == bundle["report"]


def test_cli_invalid_catalog_returns_nonzero(capsys) -> None:
    world, _ = original_demo()
    assert cli(["inspect", "--session-json", json.dumps(new_session(world)),
                "--catalog-json", '{"invalid":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
