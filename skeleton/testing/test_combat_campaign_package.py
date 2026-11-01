"""Portable combat campaign: replay, source custody and terminal acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.combat_campaign import (
    advance_campaign, finish_campaign, new_campaign, original_campaign,
)
from skeleton.game.gameplay.combat_campaign_package import (
    cli, original_package_demo, package_campaign, resume_package, verify_package,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_checkpoint_exports_and_replays_to_same_terminal_game():
    source = original_campaign()
    checkpoint = original_package_demo()
    assert checkpoint["snapshot"]["state"]["next_index"] == 1
    assert checkpoint["manifest"]["encounters"][0]["reward"] == 10
    assert verify_package(json.loads(json.dumps(checkpoint))) == checkpoint
    finished = resume_package(checkpoint)
    assert finished["snapshot"] == finish_campaign(source)
    assert finished["manifest"]["phase"] == "won"
    assert finished["manifest"]["currency"] == 30
    assert verify_package(finished) == finished
    assert resume_package(finished) == finished


def test_checkpoint_resume_matches_direct_completion_after_multiple_exports():
    source = original_campaign()
    checkpoint = advance_campaign(new_campaign(source))
    first = package_campaign(source, checkpoint)
    assert first == package_campaign(source, checkpoint)
    assert resume_package(json.loads(json.dumps(first))) == package_campaign(
        source, finish_campaign(source)
    )


@pytest.mark.parametrize("mutate", [
    lambda x: x["source"]["encounters"][0].update(reward=999),
    lambda x: x["snapshot"]["state"].update(currency=999),
    lambda x: x["manifest"].update(currency=999),
    lambda x: x["manifest"]["encounters"][0].update(reward=999),
    lambda x: x["snapshot"]["save"].update(state_digest="0" * 64),
    lambda x: x.update(snapshot_digest="0" * 64),
    lambda x: x.update(receipt="0" * 64),
    lambda x: x.update(claim="signed_by_author"),
])
def test_portable_checkpoint_tampering_fails_closed(mutate):
    bundle = copy.deepcopy(original_package_demo())
    mutate(bundle)
    with pytest.raises(CombatSessionError):
        verify_package(bundle)


def test_cannot_package_checkpoint_under_other_authored_source():
    source = original_campaign()
    snapshot = advance_campaign(new_campaign(source))
    changed = copy.deepcopy(source)
    changed["encounters"][0]["reward"] = 11
    with pytest.raises(CombatSessionError, match="source mismatch"):
        package_campaign(changed, snapshot)


def test_cli_demo_verify_resume_and_duplicate_key_rejection(capsys):
    assert cli(["demo"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["verify", "--package-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == bundle
    assert cli(["resume", "--package-json", json.dumps(bundle)]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["manifest"]["phase"] == "won"
    assert cli(["verify", "--package-json", '{"schema_version":1,"schema_version":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_cli_pack_export_matches_direct_package(capsys):
    source = original_campaign()
    snapshot = advance_campaign(new_campaign(source))
    assert cli(["pack", "--source-json", json.dumps(source),
                "--session-json", json.dumps(snapshot)]) == 0
    assert json.loads(capsys.readouterr().out) == package_campaign(source, snapshot)
