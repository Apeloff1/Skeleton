"""Source -> actual movement -> weather costs -> save/replay/authoring acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_weather import (
    build_weather_game, resume_weather_game, validate_weather,
    verify_weather_game, weather_forecast, verify_weather_forecast,
)
from skeleton.game.gameplay.harbor_crafting_weather_authoring import (
    edit_weather, verify_weather_edit,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def source_board():
    world = load_source(FIXTURES / "harbor_lantern_quay.json")
    board = decode((FIXTURES / "harbor_lantern_quay_weather.json").read_bytes())
    return world, board


def test_storms_and_hazards_apply_to_actual_movement_and_replay():
    world, board = source_board()
    report = build_weather_game(world, board, demo_actions(), require_win=True)
    assert report["bundle"]["state"]["ending"] == "beacon"
    assert report["storm_moves"] > 0
    assert report["hazard_counts"] == {"slippery_stairs": 1, "dock_spray": 1}
    assert report["energy"] < board["max_energy"]
    assert report["events"][-1]["position"] == [5, 3]
    assert verify_weather_game(decode(canonical(report)), require_win=True)["energy"] == report["energy"]
    assert [entry["tick"] for entry in report["events"]] == list(range(1, len(demo_actions())+1))


def test_rest_can_recover_but_exhausted_actions_are_denied():
    world, board = source_board()
    low = deepcopy(board)
    low["max_energy"] = 3
    with pytest.raises(HarborError, match="exhaustion"):
        build_weather_game(world, low, demo_actions())
    safe = build_weather_game(world, low, [
        {"op": "move", "direction": "east"}, {"op": "wait"},
        {"op": "gather"}, {"op": "wait"},
    ])
    assert safe["rest_ticks"] == 2 and safe["energy"] >= 0
    assert verify_weather_game(safe)["energy"] == safe["energy"]


def test_resume_lease_and_exact_history_replay():
    world, board = source_board()
    actions = demo_actions()
    partial = build_weather_game(world, board, actions[:8])
    final = resume_weather_game(partial, actions[8:],
                                expected_digest=partial["report_digest"], require_win=True)
    assert final == build_weather_game(world, board, actions, require_win=True)
    with pytest.raises(HarborError, match="stale"):
        resume_weather_game(partial, actions[8:], expected_digest="0"*64)
    with pytest.raises(HarborError, match="already complete"):
        resume_weather_game(final, [], expected_digest=final["report_digest"])


def test_forecast_is_source_bound_and_replay_verified():
    world, board = source_board()
    partial = build_weather_game(world, board, demo_actions()[:3])
    forecast = weather_forecast(partial, horizon=12)
    assert forecast["rows"][0] == {"tick": 4, "weather": "clear"}
    assert any(row["weather"] == "storm" for row in forecast["rows"])
    assert verify_weather_forecast(decode(canonical(forecast)))["rows"] == forecast["rows"]
    forged = deepcopy(forecast)
    forged["rows"][0]["weather"] = "storm"
    forged["forecast_digest"] = digest({k: v for k, v in forged.items() if k != "forecast_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_weather_forecast(forged)


def test_resealed_overlay_forgery_and_invalid_boards_fail_closed():
    world, board = source_board()
    original = build_weather_game(world, board, demo_actions())
    for key, mutate in (
        ("energy", lambda v: v + 1),
        ("storm_moves", lambda v: v + 1),
        ("events", lambda v: v[:-1]),
        ("hazard_counts", lambda v: {**v, "dock_spray": 0}),
    ):
        forged = deepcopy(original)
        forged[key] = mutate(forged[key])
        forged["report_digest"] = digest({k: v for k, v in forged.items() if k != "report_digest"})
        with pytest.raises(HarborError, match="replay"):
            verify_weather_game(forged)
    for bad in (
        {**board, "max_energy": True},
        {**board, "phases": [{"tick": 1, "kind": "clear"}]},
        {**board, "phases": board["phases"] + [board["phases"][0]]},
        {**board, "hazards": board["hazards"] + [board["hazards"][0]]},
        {**board, "hazards": [{**board["hazards"][0], "at": [0, 0]}]},
    ):
        with pytest.raises(HarborError):
            validate_weather(bad, world)


def test_editor_preview_is_transactional_and_replays_old_history():
    world, board = source_board()
    report = build_weather_game(world, board, demo_actions(), require_win=True)
    edits = [{"target": "phase", "id": 1, "field": "kind", "value": "rain"}]
    revision = edit_weather(
        world, board, edits, expected_source_digest=digest(world),
        expected_board_digest=digest(board), preview_report=report,
    )
    assert revision["preview"]["after_energy"] > revision["preview"]["before_energy"]
    assert verify_weather_edit(decode(canonical(revision)))["hazards"] == 2
    with pytest.raises(HarborError, match="stale"):
        edit_weather(world, board, edits, expected_source_digest="0"*64,
                     expected_board_digest=digest(board))
    forged = deepcopy(revision)
    forged["after"]["phases"][1]["kind"] = "night"
    forged["after_digest"] = digest(forged["after"])
    forged["revision_digest"] = digest({k: v for k, v in forged.items() if k != "revision_digest"})
    with pytest.raises(HarborError, match="replay"):
        verify_weather_edit(forged)


def test_cli_play_forecast_resume_and_edit(tmp_path):
    world, board = source_board()
    board_file = tmp_path / "weather.json"
    board_file.write_bytes(canonical(board))
    actions_file = tmp_path / "actions.json"
    actions_file.write_bytes(canonical(demo_actions()[:8]))

    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)

    partial = call("weather-run", "--weather-board", str(board_file),
                   "--actions", str(actions_file))
    report_file = tmp_path / "report.json"
    report_file.write_bytes(canonical(partial))
    assert call("weather-verify", "--weather-report", str(report_file))["verified"]
    forecast = call("weather-forecast", "--weather-report", str(report_file))
    forecast_file = tmp_path / "forecast.json"
    forecast_file.write_bytes(canonical(forecast))
    assert call("weather-verify-forecast", "--weather-forecast", str(forecast_file))["verified"]
    actions_file.write_bytes(canonical(demo_actions()[8:]))
    final = call("weather-resume", "--weather-report", str(report_file),
                 "--actions", str(actions_file),
                 "--expected-weather-digest", partial["report_digest"], "--require-win")
    assert final["bundle"]["state"]["ending"] == "beacon"
    edits_file = tmp_path / "edits.json"
    edits_file.write_bytes(canonical([{"target": "phase", "id": 1, "field": "kind", "value": "rain"}]))
    report_file.write_bytes(canonical(final))
    revision = call("weather-author", "--weather-board", str(board_file),
                    "--weather-edits", str(edits_file), "--weather-report", str(report_file),
                    "--expected-source-digest", digest(world),
                    "--expected-weather-board-digest", digest(board))
    revision_file = tmp_path / "revision.json"
    revision_file.write_bytes(canonical(revision))
    assert call("weather-verify-author", "--weather-revision", str(revision_file))["verified"]
    denied = subprocess.run(
        CLI + ["weather-resume", "--weather-report", str(report_file),
               "--actions", str(actions_file), "--expected-weather-digest", "0"*64],
        capture_output=True, check=False,
    )
    assert denied.returncode == 2 and not denied.stdout
