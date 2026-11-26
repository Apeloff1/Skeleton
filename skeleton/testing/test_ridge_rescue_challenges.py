"""All eight original terrain scenarios must earn real engine outcomes."""
from copy import deepcopy
import pytest

from skeleton.game.gameplay.ridge_rescue.challenges import (
    ChallengeError, list_challenges, load_challenge, parse_challenge, play_challenge,
)
from skeleton.game.gameplay.ridge_rescue.custody import verify_run, digest
from skeleton.game.gameplay.ridge_rescue.challenges_cli import main


def test_all_eight_original_challenges_are_playable():
    catalog = list_challenges()
    assert catalog["count"] == 8
    seen = set()
    for entry in catalog["challenges"]:
        assert entry["id"] not in seen
        seen.add(entry["id"])
        challenge = load_challenge(entry["id"])
        verified = verify_run(play_challenge(entry["id"]))
        assert verified["state"]["status"] == "won:" + challenge["ending"]
        assert all(v == "rescued" for v in verified["state"]["civilians"].values())
        assert entry["source_sha256"] == digest(challenge)


def test_invalid_or_unearned_scenario_rejected():
    original = load_challenge("north-pass")
    forged = deepcopy(original)
    forged["actions"] = [{"verb": "evacuate", "choice": "protect"}]
    with pytest.raises(ChallengeError):
        parse_challenge(forged)
    with pytest.raises(ChallengeError):
        load_challenge("../secrets")
    with pytest.raises(ChallengeError):
        load_challenge("missing")


def test_cli_list_and_play(capsys):
    assert main(["list"]) == 0
    import json
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["count"] == 8
    assert main(["play", "--id", "beacon-approach"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert verify_run(bundle)["state"]["status"] == "won:protect"


def test_cli_refuses_overwrite(tmp_path):
    output = tmp_path / "challenge.json"
    assert main(["play", "--id", "north-pass", "--output", str(output)]) == 0
    with pytest.raises(SystemExit) as exc:
        main(["play", "--id", "north-pass", "--output", str(output)])
    assert exc.value.code == 2
