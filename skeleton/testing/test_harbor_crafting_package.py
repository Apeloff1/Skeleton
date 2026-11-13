"""Portable game package production, replay, source provenance and CLI."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_package import (
    build_package, play_package, verify_package, verify_package_play,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def source():
    return load_source(ROOT / "harbor_lantern_quay.json")


def board():
    return decode((ROOT / "harbor_lantern_quay_missions.json").read_bytes())


def package():
    return build_package(source(), board())


def test_original_game_packaging_includes_real_earned_victory_and_manifest():
    built = package()
    assert built["id"] == "lantern-quay"
    assert [entry["path"] for entry in built["manifest"]] == [
        "board.json", "demo-report.json", "world.json",
    ]
    assert built["demo"]["points"] == 60
    assert built["demo"]["bundle"]["state"]["ending"] == "beacon"
    verified = verify_package(decode(canonical(built)))
    assert verified["demo_points"] == 60
    assert verified["demo_ending"] == "beacon"
    assert canonical(package()) == canonical(built)


def test_player_actions_execute_against_packaged_world_with_replay_custody():
    built = package()
    play = play_package(built, demo_actions(), require_all=True)
    assert play["report"]["bundle"]["state"]["ending"] == "beacon"
    assert verify_package_play(decode(canonical(play)), require_all=True)["points"] == 60
    assert canonical(play_package(built, demo_actions(), require_all=True)) == canonical(play)


def test_partial_gameplay_is_exportable_but_never_falsely_claims_all_missions():
    play = play_package(package(), demo_actions()[:5])
    assert play["report"]["completed"] == ["salvage"]
    assert play["report"]["points"] == 10
    with pytest.raises(HarborError, match="not fully earned"):
        verify_package_play(play, require_all=True)


@pytest.mark.parametrize("mutation", [
    lambda p: p["manifest"][0].update({"bytes": 1}),
    lambda p: p["manifest"][1].update({"sha256": "0" * 64}),
    lambda p: p["demo"].update({"points": 999}),
    lambda p: p["board"]["missions"][0].update({"points": 99}),
    lambda p: p["source"].update({"initial_coins": 99}),
    lambda p: p.update({"choice": "shelter"}),
    lambda p: p.update({"id": "other-world"}),
])
def test_package_forgery_rejected_even_if_outer_digest_is_resealed(mutation):
    built = package()
    mutation(built)
    built["package_digest"] = digest({key: value for key, value in built.items() if key != "package_digest"})
    with pytest.raises(HarborError):
        verify_package(built)


def test_play_rejects_forged_actions_and_resealed_mission_awards():
    play = play_package(package(), demo_actions())
    forged = deepcopy(play)
    forged["report"]["points"] = 900
    forged["play_digest"] = digest({key: value for key, value in forged.items() if key != "play_digest"})
    with pytest.raises(HarborError):
        verify_package_play(forged)
    forged = deepcopy(play)
    forged["actions"][0]["direction"] = "west"
    forged["play_digest"] = digest({key: value for key, value in forged.items() if key != "play_digest"})
    with pytest.raises(HarborError):
        verify_package_play(forged)


def test_cli_package_build_verify_play_and_verify_play(tmp_path):
    source_path = ROOT / "harbor_lantern_quay.json"
    board_path = ROOT / "harbor_lantern_quay_missions.json"
    actions_path = tmp_path / "actions.json"
    actions_path.write_bytes(canonical(demo_actions()))
    base = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    built = subprocess.run(
        base + ["package-build", "--source", str(source_path), "--missions", str(board_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert built.returncode == 0, built.stderr
    package_path = tmp_path / "package.json"
    package_path.write_text(built.stdout, encoding="utf-8")
    verified = subprocess.run(
        base + ["package-verify", "--package", str(package_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["verified"]
    played = subprocess.run(
        base + ["package-play", "--package", str(package_path),
                "--actions", str(actions_path), "--require-all"],
        capture_output=True, text=True, timeout=30,
    )
    assert played.returncode == 0, played.stderr
    play_path = tmp_path / "play.json"
    play_path.write_text(played.stdout, encoding="utf-8")
    accepted = subprocess.run(
        base + ["package-verify-play", "--play", str(play_path), "--require-all"],
        capture_output=True, text=True, timeout=30,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["points"] == 60


def test_package_rejects_noncanonical_payloads_and_oversized_actions():
    built = package()
    with pytest.raises(HarborError, match="list"):
        play_package(built, {"op": "wait"})
    with pytest.raises(HarborError):
        play_package(built, [{"op": "wait"}] * (built["source"]["max_ticks"] + 1))
    forged = deepcopy(built)
    forged["manifest"] = list(reversed(forged["manifest"]))
    forged["package_digest"] = digest({key: value for key, value in forged.items() if key != "package_digest"})
    with pytest.raises(HarborError, match="manifest"):
        verify_package(forged)


def test_package_inputs_remain_immutable_through_verified_play():
    original_source = source()
    original_board = board()
    before_source, before_board = deepcopy(original_source), deepcopy(original_board)
    built = build_package(original_source, original_board)
    played = play_package(built, demo_actions())
    assert verify_package_play(played)["ending"] == "beacon"
    assert original_source == before_source
    assert original_board == before_board
