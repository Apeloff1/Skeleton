"""Original player choices earn only canonical, replay-verified league consequences."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_solver import solve_league
from skeleton.game.gameplay.harbor_crafting_convoy_league_consequences import (
    build_league_consequences, compare_league_choices, verify_league_consequences,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_consequence_package import (
    build_choice_package, play_choice_package, verify_choice_package_play,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league_package import build_league_package

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def game():
    source = load_source(FIXTURES / "harbor_lantern_quay.json")
    league = decode((FIXTURES / "harbor_lantern_quay_convoy_league.json").read_bytes())
    contracts = decode((FIXTURES / "harbor_lantern_quay_convoy_league_contracts.json").read_bytes())
    save = solve_league(source, league)["save"]
    return source, league, contracts, save


def test_mutually_exclusive_reputation_and_salvage_credits():
    source, league, contracts, save = game()
    relief = build_league_consequences(save, contracts, ["relief", "relief"], require_all=True)
    salvage = build_league_consequences(save, contracts, ["salvage", "salvage"], require_all=True)
    mixed = build_league_consequences(save, contracts, ["relief", "salvage"], require_all=True)
    assert relief["complete"] and salvage["complete"] and mixed["complete"]
    assert relief["reputation"] > 0 and relief["credits"] == 0
    assert salvage["credits"] > 0 and salvage["reputation"] == 0
    assert mixed["credits"] > 0 and mixed["reputation"] > 0
    assert len(mixed["tokens"]) == 10
    assert verify_league_consequences(decode(canonical(mixed)), require_all=True)["verified"]
    comparison = compare_league_choices(save, contracts)
    assert comparison["shared_gameplay_digest"] == save["save_digest"]


def test_reject_unearned_choice_and_resealed_forgery():
    source, league, contracts, save = game()
    partial = deepcopy(save)
    # A legitimate partial save is rebuilt rather than altering a finished save.
    from skeleton.game.gameplay.harbor_crafting_convoy_league import build_league
    partial = build_league(source, league, [save["sessions"][0][:15]])
    with pytest.raises(HarborError, match="not earned"):
        build_league_consequences(partial, contracts, ["relief"], require_all=True)
    with pytest.raises(HarborError, match="choices"):
        build_league_consequences(save, contracts, ["relief"])
    bad = deepcopy(contracts)
    bad[1]["contracts"][2]["target"] = "nonexistent"
    with pytest.raises(HarborError):
        build_league_consequences(save, bad, ["relief", "salvage"])
    result = build_league_consequences(save, contracts, ["relief", "salvage"])
    forged = deepcopy(result)
    forged["credits"] = 999999
    forged["report_digest"] = digest({
        k: v for k, v in forged.items() if k != "report_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_league_consequences(forged)


def test_choice_package_source_bound_and_portable():
    source, league, contracts, save = game()
    package = build_choice_package(
        "harbor_choice_championship",
        build_league_package("harbor_championship", source, league), contracts,
    )
    play = play_choice_package(package, save, ["relief", "salvage"], require_all=True)
    assert verify_choice_package_play(decode(canonical(play)), require_all=True)["complete"]
    with pytest.raises(HarborError, match="source mismatch"):
        from skeleton.game.gameplay.harbor_crafting_convoy_league import build_league
        changed_league = deepcopy(league)
        changed_league["target_score"] += 1
        changed = build_league(source, changed_league, save["sessions"])
        play_choice_package(package, changed, ["relief", "salvage"])


def test_cli_consequences_and_package(tmp_path):
    source, league, contracts, save = game()
    def write(name, value):
        path = tmp_path / (name + ".json")
        path.write_bytes(canonical(value))
        return str(path)
    def call(*args):
        result = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()
        return decode(result.stdout)
    save_path = write("save", save)
    contracts_path = write("contracts", contracts)
    choices_path = write("choices", ["relief", "salvage"])
    report = call("league-consequences", "--league-save", save_path,
                  "--league-contracts", contracts_path,
                  "--league-choices", choices_path, "--require-all")
    assert call("league-verify-consequences", "--league-consequences",
                write("report", report), "--require-all")["complete"]
    league_package = build_league_package("championship", source, league)
    package = call("league-choice-package", "--league-package",
                   write("league_package", league_package),
                   "--league-contracts", contracts_path)
    play = call("league-choice-play", "--league-choice-package",
                write("choice_package", package), "--league-save", save_path,
                "--league-choices", choices_path, "--require-all")
    assert call("league-choice-verify-play", "--league-choice-play",
                write("choice_play", play), "--require-all")["verified"]
