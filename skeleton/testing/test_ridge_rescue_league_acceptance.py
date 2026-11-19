"""Two-entrant league acceptance from real gameplay and immutable exports."""
from copy import deepcopy
import json
import pytest

from skeleton.game.gameplay.ridge_rescue.league_acceptance import run_acceptance, main
from skeleton.game.gameplay.ridge_rescue.league import verify_league_export, LeagueError
from skeleton.game.gameplay.ridge_rescue.custody import digest


def test_two_entrant_gameplay_to_verified_league():
    bundle = run_acceptance()
    checked = verify_league_export(bundle)
    assert checked["entries"] == 2
    assert checked["champion"] == "ridge-protectors"
    assert checked["ranking"][0]["rank"] == 1
    assert checked["ranking"][1]["rank"] == 2
    assert checked["ranking"][0]["score"] > checked["ranking"][1]["score"]


def test_acceptance_is_reproducible():
    assert run_acceptance() == run_acceptance()


def test_rejects_rewritten_game_result_even_with_fresh_outer_hash():
    bundle = run_acceptance()
    forged = deepcopy(bundle)
    forged["payload"]["board"]["entries"][0]["result"]["health"] = 100
    forged["payload"]["board"]["head"] = digest({
        k: v for k, v in forged["payload"]["board"].items() if k != "head"
    })
    forged["sha256"] = digest(forged["payload"])
    with pytest.raises(LeagueError):
        verify_league_export(forged)


def test_cli_emits_real_portable_league(capsys):
    assert main([]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert verify_league_export(bundle)["entries"] == 2


def test_cli_no_overwrite(tmp_path):
    path = tmp_path / "league-acceptance.json"
    assert main(["--output", str(path)]) == 0
    with pytest.raises(SystemExit) as exc:
        main(["--output", str(path)])
    assert exc.value.code == 2
