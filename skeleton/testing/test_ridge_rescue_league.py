"""Original rescue championship with replay-derived points and CAS custody."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from skeleton.game.gameplay.ridge_rescue.custody import digest, export_run
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.league import (
    LeagueError, parse_league, open_league, verify_league, submit_run,
    export_league, verify_league_export,
)

HERE = Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue"


def source():
    return json.loads((HERE / "cinder_ridge_league.json").read_text(encoding="utf-8"))


def run(choice):
    world = parse_world(source()["world"])
    return export_run(world, acceptance_actions(choice))


def test_two_earned_endings_and_deterministic_ranking():
    board = open_league(source())
    first = submit_run(board, expected_head=board["head"], handle="ridge-hero", run=run("protect"))
    second = submit_run(first, expected_head=first["head"], handle="salvage-crew", run=run("salvage"))
    checked = verify_league(second)
    assert checked["entries"] == 2
    assert checked["champion"] == "ridge-hero"
    assert checked["ranking"][0]["score"] > checked["ranking"][1]["score"]
    assert checked["ranking"][0]["status"] == "won:protect"
    assert verify_league_export(export_league(second))["head"] == second["head"]
    assert board["entries"] == []


def test_rejects_stale_cas_duplicate_and_wrong_world():
    board = open_league(source())
    first = submit_run(board, expected_head=board["head"], handle="ridge-hero", run=run("protect"))
    with pytest.raises(LeagueError, match="stale"):
        submit_run(first, expected_head=board["head"], handle="new-crew", run=run("salvage"))
    with pytest.raises(LeagueError, match="already"):
        submit_run(first, expected_head=first["head"], handle="ridge-hero", run=run("salvage"))
    forged = deepcopy(run("protect"))
    forged["payload"]["world"]["name"] = "Unrelated source"
    forged["sha256"] = digest(forged["payload"])
    with pytest.raises(LeagueError):
        submit_run(first, expected_head=first["head"], handle="new-crew", run=forged)


def test_rejects_forged_scores_even_with_recomputed_board_head():
    board = open_league(source())
    board = submit_run(board, expected_head=board["head"], handle="ridge-hero", run=run("protect"))
    board["entries"][0]["result"]["score"] += 1_000_000
    board["head"] = digest({k: v for k, v in board.items() if k != "head"})
    with pytest.raises(LeagueError):
        verify_league(board)


def test_rejects_tampered_portable_ranking():
    board = submit_run(open_league(source()), expected_head=open_league(source())["head"],
                       handle="ridge-hero", run=run("protect"))
    export = export_league(board)
    export["payload"]["ranking"][0]["score"] = 9_999_999
    export["sha256"] = digest(export["payload"])
    with pytest.raises(LeagueError):
        verify_league_export(export)


def test_invalid_source_and_unearned_run():
    bad = source()
    bad["objective"] = "admin"
    with pytest.raises(LeagueError):
        parse_league(bad)
    board = open_league(source())
    world = parse_world(source()["world"])
    with pytest.raises(LeagueError, match="victories"):
        submit_run(board, expected_head=board["head"], handle="no-victory",
                   run=export_run(world, []))
