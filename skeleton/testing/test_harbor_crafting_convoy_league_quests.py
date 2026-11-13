"""Original cross-round quests: earned prerequisites, editor, CLI and replay."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league import build_league
from skeleton.game.gameplay.harbor_crafting_convoy_league_solver import solve_league
from skeleton.game.gameplay.harbor_crafting_convoy_league_quests import (
    build_league_quest_report, league_quest_status, validate_league_quests,
    verify_league_quest_report,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_quest_authoring import (
    edit_league_quests, verify_league_quest_revision,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def game():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    league = decode((FIXTURES / "harbor_lantern_quay_convoy_league.json").read_bytes())
    board = decode((FIXTURES / "harbor_lantern_quay_convoy_league_quests.json").read_bytes())
    save = solve_league(source, league)["save"]
    return source, league, board, save


def test_cross_round_objectives_require_earned_gameplay():
    source, league, board, save = game()
    result = build_league_quest_report(save, board, require_all=True)
    assert result["complete"] and result["points"] == 38
    assert len(result["awards"]) == 6
    assert verify_league_quest_report(decode(canonical(result)), require_all=True)["verified"]
    assert league_quest_status(result)["remaining"] == []
    partial = build_league(source, league, [save["sessions"][0]])
    not_yet = build_league_quest_report(partial, board)
    assert not not_yet["complete"]
    assert len(not_yet["awards"]) == 3
    with pytest.raises(HarborError, match="not earned"):
        build_league_quest_report(partial, board, require_all=True)


def test_board_dag_rejects_cycles_unknown_enemy_and_bool_points():
    source, league, board, save = game()
    variants = []
    cycle = deepcopy(board)
    cycle["objectives"][0]["requires"] = ["homecoming"]
    variants.append(cycle)
    unknown = deepcopy(board)
    unknown["objectives"][4]["target"] = "not_a_raider"
    variants.append(unknown)
    bool_points = deepcopy(board)
    bool_points["objectives"][2]["points"] = True
    variants.append(bool_points)
    nonhashable = deepcopy(board)
    nonhashable["objectives"][2]["requires"] = [{"forged": "dependency"}]
    variants.append(nonhashable)
    for variant in variants:
        with pytest.raises(HarborError):
            validate_league_quests(variant, save)


def test_resealed_quest_forgery_and_transactional_editor():
    source, league, board, save = game()
    report = build_league_quest_report(save, board)
    forged = deepcopy(report)
    forged["points"] = 999
    forged["report_digest"] = digest({
        k: v for k, v in forged.items() if k != "report_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_league_quest_report(forged)
    edits = [{"kind": "minimum-points", "target": "board", "value": 39}]
    revision = edit_league_quests(
        save, board, edits, expected_digest=digest(board), preview=True,
    )
    assert not revision["after_preview"]["complete"]
    assert verify_league_quest_revision(decode(canonical(revision)))["verified"]
    with pytest.raises(HarborError, match="stale"):
        edit_league_quests(save, board, edits, expected_digest="0" * 64)


def test_cli_quests_author_and_verification(tmp_path):
    source, league, board, save = game()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    save_file = write("save", save)
    board_file = str(FIXTURES / "harbor_lantern_quay_convoy_league_quests.json")
    report = call("league-quests", "--league-save", save_file,
                  "--league-quest-board", board_file, "--require-all")
    assert call("league-verify-quests", "--league-quest-report",
                write("report", report), "--require-all")["complete"]
    assert call("league-quest-status", "--league-quest-report",
                write("report2", report))["remaining"] == []
    revision = call("league-quest-author", "--league-save", save_file,
        "--league-quest-board", board_file, "--league-quest-edits",
        write("edits", [{"kind": "minimum-points", "target": "board", "value": 39}]),
        "--expected-league-quest-board-digest", digest(board), "--league-quest-preview")
    assert call("league-verify-quest-author", "--league-quest-revision",
                write("revision", revision))["verified"]
