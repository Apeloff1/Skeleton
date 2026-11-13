"""Source-bound tournament acceptance: bracket, replay, persistence and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_tournament import (
    CombatSessionError, advance_tournament, cli, export_tournament,
    finish_tournament, import_tournament, new_tournament,
    normalize_tournament, original_tournament, verify_tournament,
)


def test_original_bracket_is_playable_and_replay_verified() -> None:
    result = finish_tournament(original_tournament())
    assert result["state"]["phase"] == "won"
    assert result["state"]["next_match"] == 3
    assert len(result["state"]["matches"]) == 3
    assert result["state"]["champion"] == result["state"]["matches"][2]["winner"]
    assert result["state"]["matches"][2]["left"] == result["state"]["matches"][0]["winner"]
    assert result["state"]["matches"][2]["right"] == result["state"]["matches"][1]["winner"]
    assert verify_tournament(json.loads(json.dumps(result))) == result


def test_resume_and_portable_export_are_identical_to_one_pass() -> None:
    source = original_tournament()
    first = advance_tournament(new_tournament(source))
    second = advance_tournament(first)
    result = finish_tournament(source, resume=json.loads(json.dumps(second)))
    assert result == finish_tournament(source)
    bundle = export_tournament(result)
    assert import_tournament(json.loads(json.dumps(bundle))) == result
    assert first == advance_tournament(new_tournament(source))


def test_mutated_winner_or_hp_or_save_lineage_fails_closed() -> None:
    result = finish_tournament(original_tournament())
    for path in ("winner", "hp", "parent"):
        broken = copy.deepcopy(result)
        if path == "winner":
            broken["state"]["matches"][0]["winner"] = "forged"
        elif path == "hp":
            actor = broken["state"]["matches"][0]["combat"]["scenario"]["actors"][0]["id"]
            broken["state"]["matches"][0]["combat"]["state"]["actors"][actor]["hp"] = 900
        else:
            broken["save"]["parent_save_digest"] = "0" * 64
        with pytest.raises(CombatSessionError, match="mismatch"):
            verify_tournament(broken)


def test_portable_checksum_and_identity_cannot_be_swapped() -> None:
    bundle = export_tournament(new_tournament(original_tournament()))
    bad = copy.deepcopy(bundle)
    bad["checksum"] = "0" * 64
    with pytest.raises(CombatSessionError, match="checksum"):
        import_tournament(bad)
    bad = copy.deepcopy(bundle)
    bad["source_digest"] = "0" * 64
    with pytest.raises(CombatSessionError, match="checksum"):
        import_tournament(bad)


@pytest.mark.parametrize("mutation", [
    lambda s: s["entrants"].append(s["entrants"][0]),
    lambda s: s["entrants"][0].update(id=s["entrants"][1]["id"]),
    lambda s: s["entrants"][0].update(attack=True),
    lambda s: s["entrants"][0].update(max_hp=0),
    lambda s: s.update(match_turn_limit=65),
    lambda s: s.update(untrusted="extra"),
    lambda s: s["entrants"][0].update(team="forged"),
])
def test_hostile_source_is_rejected(mutation) -> None:
    source = original_tournament()
    mutation(source)
    with pytest.raises(CombatSessionError):
        normalize_tournament(source)


def test_changed_source_cannot_resume() -> None:
    source = original_tournament()
    saved = advance_tournament(new_tournament(source))
    changed = copy.deepcopy(source)
    changed["entrants"][1]["attack"] += 1
    with pytest.raises(CombatSessionError, match="source mismatch"):
        finish_tournament(changed, resume=saved)


def test_cli_demo_advance_verify_and_export(capsys) -> None:
    assert cli(["demo"]) == 0
    complete = json.loads(capsys.readouterr().out)
    assert complete["state"]["phase"] in ("won", "draw")
    assert cli(["verify", "--session-json", json.dumps(complete)]) == 0
    assert json.loads(capsys.readouterr().out) == complete
    assert cli(["export", "--session-json", json.dumps(complete)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == complete


def test_cli_rejects_invalid_source_without_awarding_winner(capsys) -> None:
    assert cli(["simulate", "--source-json", '{"invalid":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
