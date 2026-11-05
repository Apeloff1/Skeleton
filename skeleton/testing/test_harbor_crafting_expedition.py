"""Full authored original expedition: NPC choice, weather, survey, save and package."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_expedition import (
    build_expedition, build_expedition_package, expedition_status,
    play_expedition_package, resume_expedition, verify_expedition,
    verify_expedition_package, verify_expedition_package_play,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def sources():
    world = load_source(FIXTURES / "harbor_lantern_quay.json")
    def board(name):
        return decode((FIXTURES / ("harbor_lantern_quay_" + name + ".json")).read_bytes())
    return world, board("survey"), board("weather"), board("dialogue")


def actions():
    base = demo_actions()
    return base[:16] + [
        {"op": "wait"}, {"op": "talk", "node": "merchant_intro", "choice": "permit"},
    ] + base[16:]


def test_one_actual_world_history_drives_all_three_earned_systems():
    source, survey, weather, dialogue = sources()
    report = build_expedition(source, survey, weather, dialogue, actions(),
                              require_complete=True)
    assert report["complete"] and report["survey"]["score"] == 13
    assert report["weather"]["storm_moves"] > 0
    assert report["dialogue"]["flags"] == ["dock_pass"]
    assert report["dialogue"]["bundle"] == report["survey"]["bundle"]
    assert report["dialogue"]["bundle"] == report["weather"]["bundle"]
    assert verify_expedition(decode(canonical(report)), require_complete=True)["complete"]
    status = expedition_status(report)
    assert status["delivery_permit"] and status["required_sites_remaining"] == []
    assert status["ending"] == "beacon"


def test_incomplete_and_wrong_choice_are_not_earned_victories():
    source, survey, weather, dialogue = sources()
    with pytest.raises(HarborError, match="permit"):
        build_expedition(source, survey, weather, dialogue, demo_actions())
    incomplete = build_expedition(source, survey, weather, dialogue, actions()[:10])
    assert not incomplete["complete"] and expedition_status(incomplete)["required_sites_remaining"]
    with pytest.raises(HarborError, match="not earned"):
        build_expedition(source, survey, weather, dialogue, actions()[:10],
                         require_complete=True)


def test_cas_resume_replays_all_layers_and_rejects_stale():
    source, survey, weather, dialogue = sources()
    full = actions()
    partial = build_expedition(source, survey, weather, dialogue, full[:17])
    completed = resume_expedition(partial, full[17:],
                                  expected_digest=partial["expedition_digest"],
                                  require_complete=True)
    assert completed == build_expedition(source, survey, weather, dialogue, full,
                                         require_complete=True)
    with pytest.raises(HarborError, match="stale"):
        resume_expedition(partial, full[17:], expected_digest="0"*64)
    with pytest.raises(HarborError, match="already complete"):
        resume_expedition(completed, [], expected_digest=completed["expedition_digest"])


def test_resealed_cross_layer_forgeries_rejected():
    source, survey, weather, dialogue = sources()
    original = build_expedition(source, survey, weather, dialogue, actions())
    for key, field, new_value in (
        ("survey", "score", 999),
        ("weather", "energy", 999),
        ("dialogue", "trust", 999),
    ):
        forged = deepcopy(original)
        forged[key][field] = new_value
        inner_digest = {"survey": "report_digest", "weather": "report_digest",
                        "dialogue": "report_digest"}[key]
        forged[key][inner_digest] = digest({
            k: v for k, v in forged[key].items() if k != inner_digest
        })
        forged["expedition_digest"] = digest({
            k: v for k, v in forged.items() if k != "expedition_digest"
        })
        with pytest.raises(HarborError):
            verify_expedition(forged)


def test_original_portable_package_play_and_replay():
    source, survey, weather, dialogue = sources()
    package = build_expedition_package("lantern_quay_expedition", source, survey,
                                       weather, dialogue)
    assert verify_expedition_package(decode(canonical(package)))["id"] == "lantern_quay_expedition"
    play = play_expedition_package(package, actions(), require_complete=True)
    assert verify_expedition_package_play(decode(canonical(play)),
                                          require_complete=True)["complete"]
    tampered = deepcopy(play)
    tampered["package"]["weather_board"]["max_energy"] = 1
    tampered["package"]["package_digest"] = digest({
        k: v for k, v in tampered["package"].items() if k != "package_digest"
    })
    tampered["play_digest"] = digest({k: v for k, v in tampered.items() if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_expedition_package_play(tampered)


def test_cli_source_to_replay_package_and_checkpoint(tmp_path):
    source, survey, weather, dialogue = sources()
    files = {}
    for name, board in (("survey", survey), ("weather", weather), ("dialogue", dialogue)):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(board))
        files[name] = str(path)
    actions_file = tmp_path / "actions.json"
    actions_file.write_bytes(canonical(actions()[:17]))

    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)

    board_args = [
        "--survey-board", files["survey"],
        "--weather-board", files["weather"],
        "--dialogue-board", files["dialogue"],
    ]
    partial = call("expedition-run", *board_args, "--actions", str(actions_file))
    report_file = tmp_path / "report.json"
    report_file.write_bytes(canonical(partial))
    assert call("expedition-status", "--expedition", str(report_file))["energy"] >= 0
    assert call("expedition-verify", "--expedition", str(report_file))["verified"]
    actions_file.write_bytes(canonical(actions()[17:]))
    completed = call("expedition-resume", "--expedition", str(report_file),
                     "--actions", str(actions_file),
                     "--expected-expedition-digest", partial["expedition_digest"],
                     "--require-all")
    assert completed["complete"]
    package = call("expedition-build", *board_args)
    package_file = tmp_path / "package.json"
    package_file.write_bytes(canonical(package))
    assert call("expedition-verify-package", "--expedition-package", str(package_file))["verified"]
    actions_file.write_bytes(canonical(actions()))
    play = call("expedition-play", "--expedition-package", str(package_file),
                "--actions", str(actions_file), "--require-all")
    play_file = tmp_path / "play.json"
    play_file.write_bytes(canonical(play))
    assert call("expedition-verify-play", "--expedition-play", str(play_file),
                "--require-all")["complete"]
    denied = subprocess.run(
        CLI + ["expedition-resume", "--expedition", str(report_file),
               "--actions", str(actions_file), "--expected-expedition-digest", "0"*64],
        capture_output=True, check=False,
    )
    assert denied.returncode == 2 and not denied.stdout
