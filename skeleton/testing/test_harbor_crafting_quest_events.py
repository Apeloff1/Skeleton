"""Original source -> real game -> event conditions -> replayed quest rewards."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_expedition import build_expedition
from skeleton.game.gameplay.harbor_crafting_quest_events import (
    build_quest_report, quest_status, validate_quest_board, verify_quest_report,
)
from skeleton.game.gameplay.harbor_crafting_quest_authoring import (
    edit_quest_board, verify_quest_edit,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def inputs():
    world = load_source(FIXTURES / "harbor_lantern_quay.json")
    def board(name):
        return decode((FIXTURES / ("harbor_lantern_quay_" + name + ".json")).read_bytes())
    actions = demo_actions()
    actions = actions[:16] + [
        {"op": "wait"}, {"op": "talk", "node": "merchant_intro", "choice": "permit"},
    ] + actions[16:]
    return world, board("survey"), board("weather"), board("dialogue"), board("quest_events"), actions


def expedition(count=None):
    world, survey, weather, dialogue, quests, actions = inputs()
    game = build_expedition(world, survey, weather, dialogue,
                            actions if count is None else actions[:count])
    return game, quests


def test_quest_awards_require_actual_actions_and_source_derived_prerequisites():
    game, board = expedition()
    report = build_quest_report(game, board, require_all=True)
    assert report["complete"] and report["reputation"] == 28
    assert [entry["id"] for entry in report["awards"]] == [
        "collect_timber", "craft_lantern", "merchant_permit",
        "deliver_supplies", "signal_beacon",
    ]
    assert report["tokens"] == [
        "beacon_lit", "beacon_ready", "merchant_trust",
        "supplies_delivered", "wood_found",
    ]
    assert verify_quest_report(decode(canonical(report)), require_all=True)["complete"]
    assert quest_status(report)["remaining"] == []


def test_incomplete_game_cannot_claim_rewards_or_victory():
    game, board = expedition(7)
    report = build_quest_report(game, board)
    assert not report["complete"] and "signal_beacon" in quest_status(report)["remaining"]
    with pytest.raises(HarborError, match="not earned"):
        build_quest_report(game, board, require_all=True)


def test_invalid_quest_graph_and_foreign_triggers_rejected():
    game, board = expedition()
    for bad in (
        {**board, "source_id": "foreign"},
        {**board, "quests": board["quests"] + [board["quests"][0]]},
        {**board, "quests": [{**board["quests"][0], "requires_tokens": ["future_token"]}]},
        {**board, "quests": [{**board["quests"][0], "requires_sites": ["unknown"]}]},
        {**board, "quests": [{**board["quests"][0], "reward": True}]},
        {**board, "quests": [{**board["quests"][0], "target": "unknown_resource"}]},
    ):
        with pytest.raises(HarborError):
            validate_quest_board(bad, game)


def test_resealed_event_reward_and_token_forgeries_fail_closed():
    game, board = expedition()
    original = build_quest_report(game, board)
    for key, value in (
        ("reputation", 999),
        ("tokens", ["forged"]),
        ("awards", original["awards"][:-1]),
        ("complete", False),
    ):
        forged = deepcopy(original)
        forged[key] = value
        forged["report_digest"] = digest({k: v for k, v in forged.items() if k != "report_digest"})
        with pytest.raises(HarborError, match="replay"):
            verify_quest_report(forged)


def test_transactional_quest_edit_previews_real_replay():
    game, board = expedition()
    report = build_quest_report(game, board, require_all=True)
    edits = [{"id": "signal_beacon", "field": "reward", "value": 4}]
    revision = edit_quest_board(
        game, board, edits,
        expected_expedition_digest=game["expedition_digest"],
        expected_board_digest=digest(board), preview_report=report,
    )
    assert revision["preview"]["summary"]["before_reputation"] == 28
    assert revision["preview"]["summary"]["after_reputation"] == 22
    assert verify_quest_edit(decode(canonical(revision)))["quests"] == 5
    with pytest.raises(HarborError, match="stale"):
        edit_quest_board(game, board, edits, expected_expedition_digest="0"*64,
                         expected_board_digest=digest(board))
    forged = deepcopy(revision)
    forged["after"]["quests"][-1]["reward"] = 50
    forged["after_digest"] = digest(forged["after"])
    forged["revision_digest"] = digest({k: v for k, v in forged.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_quest_edit(forged)


def test_cli_source_bound_quest_report_status_and_editor(tmp_path):
    game, board = expedition()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)

    game_file = write("game", game)
    board_file = write("board", board)
    report = call("quest-run", "--expedition", game_file,
                  "--quest-board", board_file, "--require-all")
    report_file = write("report", report)
    assert call("quest-verify", "--quest-report", report_file, "--require-all")["complete"]
    assert call("quest-status", "--quest-report", report_file)["remaining"] == []
    edits_file = write("edits", [{"id": "signal_beacon", "field": "reward", "value": 4}])
    revision = call("quest-author", "--expedition", game_file,
                    "--quest-board", board_file, "--quest-edits", edits_file,
                    "--quest-report", report_file,
                    "--expected-expedition-digest", game["expedition_digest"],
                    "--expected-quest-board-digest", digest(board))
    revision_file = write("revision", revision)
    assert call("quest-verify-author", "--quest-revision", revision_file)["verified"]
