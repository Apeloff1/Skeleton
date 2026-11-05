"""Replay-verified ghost racing and adversarial source-bound comparison."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_ghost_race import (
    ghost_race, verify_ghost_race,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def fixtures():
    world = load_source(ROOT / "harbor_lantern_quay.json")
    course = decode((ROOT / "harbor_lantern_quay_time_trial.json").read_bytes())
    return world, course


def won():
    world, _ = fixtures()
    return export_bundle(world, demo_actions(), require_win=True)


def slower():
    world, _ = fixtures()
    return export_bundle(world, [{"op": "wait"}] + demo_actions(), require_win=True)


def test_faster_player_beats_legal_slower_ghost():
    _, course = fixtures()
    race = ghost_race(won(), slower(), course)
    assert race["leader"] == "player"
    assert race["finish_delta"] == -1
    assert [entry["delta"] for entry in race["checkpoint_deltas"]] == [-1, -1, -1, -1]
    assert len(race["timeline"]) == 20
    assert race["timeline"][0]["player_pos"] == [1, 1]
    assert race["timeline"][0]["ghost_pos"] == [1, 1]
    assert verify_ghost_race(decode(canonical(race)))["leader"] == "player"


def test_ghost_can_win_and_tied_replay_is_deterministic():
    _, course = fixtures()
    assert ghost_race(slower(), won(), course)["finish_delta"] == 1
    tied = ghost_race(won(), won(), course)
    assert tied["leader"] == "tied"
    assert tied["finish_delta"] == 0
    assert canonical(tied) == canonical(ghost_race(won(), won(), course))


def test_partial_player_never_claims_ghost_victory():
    world, course = fixtures()
    partial = export_bundle(world, demo_actions()[:8])
    race = ghost_race(partial, won(), course)
    assert race["leader"] == "ghost"
    assert race["finish_delta"] is None
    assert race["checkpoint_deltas"][0]["delta"] == 0
    assert race["checkpoint_deltas"][2]["player_tick"] is None
    assert race["timeline"][-1]["player_pos"] == partial["state"]["pos"]
    assert verify_ghost_race(race)["leader"] == "ghost"


def test_ghost_requires_completed_time_trial_and_matching_world():
    world, course = fixtures()
    partial = export_bundle(world, demo_actions()[:8])
    with pytest.raises(HarborError, match="finish not earned"):
        ghost_race(won(), partial, course)
    foreign = deepcopy(world)
    foreign["initial_coins"] = 5
    with pytest.raises(HarborError, match="ghost source mismatch"):
        ghost_race(won(), export_bundle(foreign, demo_actions()), course)


def test_expected_player_lease_prevents_stale_comparison():
    _, course = fixtures()
    with pytest.raises(HarborError, match="stale"):
        ghost_race(won(), slower(), course, expected_player_terminal_digest="0" * 64)
    race = ghost_race(
        won(), slower(), course, expected_player_terminal_digest=won()["terminal_digest"],
    )
    assert race["leader"] == "player"


@pytest.mark.parametrize("mutation", [
    lambda r: r.update({"leader": "ghost"}),
    lambda r: r.update({"finish_delta": -100}),
    lambda r: r["timeline"][1].update({"player_pos": [6, 3]}),
    lambda r: r["checkpoint_deltas"][0].update({"delta": -100}),
    lambda r: r["player"]["state"].update({"coins": 1000}),
    lambda r: r["ghost"]["events"][0]["action"].update({"op": "gather"}),
])
def test_resealed_ghost_race_forgery_rejected(mutation):
    _, course = fixtures()
    race = ghost_race(won(), slower(), course)
    mutation(race)
    race["race_digest"] = digest({k: v for k, v in race.items() if k != "race_digest"})
    with pytest.raises(HarborError):
        verify_ghost_race(race)


def test_cli_ghost_race_export_and_verify(tmp_path):
    _, course = fixtures()
    player = tmp_path / "player.json"
    ghost = tmp_path / "ghost.json"
    player.write_bytes(canonical(won()))
    ghost.write_bytes(canonical(slower()))
    trial = ROOT / "harbor_lantern_quay_time_trial.json"
    result = subprocess.run(CLI + [
        "ghost-race", "--bundle", str(player), "--ghost-bundle", str(ghost),
        "--trial", str(trial),
        "--expected-terminal-digest", won()["terminal_digest"],
    ], capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode()
    race = decode(result.stdout)
    assert race["leader"] == "player"
    path = tmp_path / "race.json"
    path.write_bytes(result.stdout)
    verified = subprocess.run(CLI + [
        "ghost-verify", "--report", str(path),
    ], capture_output=True, check=False)
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["finish_delta"] == -1
