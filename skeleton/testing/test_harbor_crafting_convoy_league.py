"""Replay and adversarial acceptance for the two-stage convoy championship."""
from __future__ import annotations

from copy import deepcopy
from io import StringIO
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source, demo_actions,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league import (
    build_league, league_status, resume_league, validate_league, verify_league,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_authoring import (
    edit_league, verify_league_revision,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_package import (
    build_league_package, play_league_package, resume_league_package,
    verify_league_package, verify_league_package_play,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_ui import play_league_live

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def setup():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    league = decode((FIXTURES / "harbor_lantern_quay_convoy_league.json").read_bytes())
    return source, league


def winning_actions():
    return demo_actions()[:12] + [
        {"op": "escort"}, {"op": "move", "direction": "east"},
        {"op": "escort"}, {"op": "strike"},
        {"op": "move", "direction": "east"}, {"op": "escort"},
        {"op": "move", "direction": "east"}, {"op": "escort"},
    ]


def test_two_earned_rounds_score_and_full_replay():
    source, league = setup()
    actions = winning_actions()
    save = build_league(source, league, [actions, actions], require_complete=True)
    assert save["complete"] and not save["failed"]
    assert save["score"] == 28
    assert [row["points"] for row in save["standings"]] == [13, 15]
    assert [row["bounty"] for row in save["standings"]] == [7, 9]
    assert verify_league(decode(canonical(save)), require_complete=True)["rounds_played"] == 2
    assert league_status(save)["next_round"] is None


def test_partial_round_resume_and_exact_head_cas():
    source, league = setup()
    actions = winning_actions()
    initial = build_league(source, league, [])
    first = resume_league(initial, actions[:15], expected_digest=initial["save_digest"])
    assert league_status(first)["next_round"] == "canal_relief"
    second = resume_league(first, actions[15:], expected_digest=first["save_digest"])
    assert league_status(second)["next_round"] == "lantern_homecoming"
    finished = resume_league(second, actions, expected_digest=second["save_digest"],
                             require_complete=True)
    assert finished == build_league(source, league, [actions, actions])
    with pytest.raises(HarborError, match="stale"):
        resume_league(first, actions[15:], expected_digest=initial["save_digest"])
    with pytest.raises(HarborError, match="terminal"):
        resume_league(finished, actions, expected_digest=finished["save_digest"])


def test_reject_unearned_progression_and_destruction():
    source, league = setup()
    actions = winning_actions()
    with pytest.raises(HarborError, match="before earned"):
        build_league(source, league, [actions[:15], actions])
    destroyed = build_league(source, league, [actions[:15] + [{"op": "wait"}] * 3])
    assert destroyed["failed"]
    assert verify_league(destroyed)["failed"]
    with pytest.raises(HarborError, match="championship"):
        verify_league(destroyed, require_complete=True)
    lowered = deepcopy(league)
    lowered["rounds"][0]["minimum_hull"] = 3
    assert build_league(source, lowered, [actions])["standings"][0]["earned"]


def test_reject_bad_source_duplicate_boards_and_boolean_scores():
    source, league = setup()
    variants = []
    duplicate = deepcopy(league)
    duplicate["rounds"][1]["board"] = deepcopy(duplicate["rounds"][0]["board"])
    variants.append(duplicate)
    wrong = deepcopy(league)
    wrong["source_id"] = "foreign"
    variants.append(wrong)
    boolean = deepcopy(league)
    boolean["target_score"] = True
    variants.append(boolean)
    oversized = deepcopy(league)
    oversized["rounds"] *= 10
    variants.append(oversized)
    for candidate in variants:
        with pytest.raises(HarborError):
            validate_league(candidate, source)


def test_resealed_forged_score_and_actions_are_rejected():
    source, league = setup()
    save = build_league(source, league, [winning_actions(), winning_actions()])
    for key, value in [("score", 900), ("complete", False)]:
        forged = deepcopy(save)
        forged[key] = value
        forged["save_digest"] = digest({k: v for k, v in forged.items() if k != "save_digest"})
        with pytest.raises(HarborError, match="replay"):
            verify_league(forged)
    forged = deepcopy(save)
    forged["reports"][0]["state"]["bounty"] = 999
    forged["reports"][0]["report_digest"] = digest({
        k: v for k, v in forged["reports"][0].items() if k != "report_digest"
    })
    forged["save_digest"] = digest({k: v for k, v in forged.items() if k != "save_digest"})
    with pytest.raises(HarborError):
        verify_league(forged)


def test_portable_package_and_resume_are_replayed():
    source, league = setup()
    package = build_league_package("harbor_championship", source, league)
    assert verify_league_package(package)["verified"]
    actions = winning_actions()
    play = play_league_package(package, [actions])
    assert verify_league_package_play(play)["score"] == 13
    finished = resume_league_package(play, actions, expected_digest=play["play_digest"],
                                      require_complete=True)
    assert verify_league_package_play(finished, require_complete=True)["score"] == 28
    with pytest.raises(HarborError, match="stale"):
        resume_league_package(play, actions, expected_digest="0" * 64)
    forged = deepcopy(finished)
    forged["save"]["score"] = 999
    forged["play_digest"] = digest({k: v for k, v in forged.items() if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_league_package_play(forged)


def test_transactional_editor_and_preview_replay():
    source, league = setup()
    actions = winning_actions()
    preview = build_league(source, league, [actions, actions])
    edits = [{"kind": "target-score", "target": "league", "value": 29}]
    revision = edit_league(source, league, edits, expected_digest=digest(league),
                           preview_save=preview)
    assert revision["after_preview"]["failed"]
    assert verify_league_revision(decode(canonical(revision)))["preview_complete"] is False
    with pytest.raises(HarborError, match="stale"):
        edit_league(source, league, edits, expected_digest="0" * 64)
    with pytest.raises(HarborError, match="duplicate"):
        edit_league(source, league, edits * 2, expected_digest=digest(league))
    forged = deepcopy(revision)
    forged["after"]["target_score"] = 1
    forged["revision_digest"] = digest({
        k: v for k, v in forged.items() if k != "revision_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_league_revision(forged)


def test_live_player_reaches_championship_without_hidden_awards():
    source, league = setup()
    actions = winning_actions()
    def commands():
        return "\n".join(
            a["op"] if a["op"] in {"escort", "strike", "guard", "gather", "wait"}
            else a["op"] + " " + a.get("direction", a.get("recipe", a.get("item", "")))
            for a in actions
        ) + "\n"
    inp = StringIO(commands() + commands())
    out = StringIO()
    save = play_league_live(source, league, instream=inp, outstream=out)
    assert verify_league(save, require_complete=True)["complete"]
    assert "Round lantern_homecoming" in out.getvalue()


def test_cli_source_to_save_to_package_and_replay(tmp_path):
    source, league = setup()
    def write(name, value):
        p = tmp_path / (name + ".json")
        p.write_bytes(canonical(value))
        return str(p)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    league_file = str(FIXTURES / "harbor_lantern_quay_convoy_league.json")
    actions = winning_actions()
    sessions = write("sessions", [actions, actions])
    save = call("league-run", "--league-board", league_file, "--sessions", sessions,
                "--require-all")
    assert call("league-verify", "--league-save", write("save", save))["score"] == 28
    assert call("league-status", "--league-save", write("status", save))["next_round"] is None
    package = call("league-package-build", "--league-board", league_file)
    play = call("league-package-play", "--league-package", write("package", package),
                "--sessions", sessions, "--require-all")
    assert call("league-package-verify-play", "--league-play", write("play", play),
                "--require-all")["score"] == 28
    initial = call("league-init", "--league-board", league_file)
    first = call("league-resume", "--league-save", write("initial", initial),
                 "--actions", write("actions", actions),
                 "--expected-league-digest", initial["save_digest"])
    assert first["score"] == 13
    revision = call("league-author", "--league-board", league_file,
                    "--league-edits", write("edits", [
                        {"kind": "target-score", "target": "league", "value": 29}
                    ]), "--expected-league-board-digest", digest(league))
    assert call("league-verify-author",
                "--league-revision", write("revision", revision))["verified"]

def test_league_editor_replays_real_encounter_and_hull_changes():
    source, league = setup()
    actions = winning_actions()
    preview = build_league(source, league, [actions, actions])
    edits = [
        {"kind": "encounter-reward", "target": "canal_relief:canal_raider", "value": 10},
        {"kind": "convoy-hull", "target": "canal_relief", "value": 4},
    ]
    revision = edit_league(
        source, league, edits, expected_digest=digest(league), preview_save=preview,
    )
    assert revision["after_preview"]["standings"][0]["bounty"] == 10
    assert revision["after_preview"]["standings"][0]["hull"] == 4
    assert revision["after_preview"]["score"] == preview["score"] + 5
    assert verify_league_revision(revision)["preview_complete"]
    with pytest.raises(HarborError):
        edit_league(source, league, [
            {"kind": "encounter-strength", "target": "canal_relief:canal_raider", "value": 2}
        ], expected_digest=digest(league), preview_save=preview)
    with pytest.raises(HarborError, match="unknown"):
        edit_league(source, league, [
            {"kind": "encounter-reward", "target": "canal_relief:unknown", "value": 10}
        ], expected_digest=digest(league))
