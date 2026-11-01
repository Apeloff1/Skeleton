"""Deterministic objectives: authored source -> canonical play -> save -> export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_objectives import (
    SCHEMA, advance_objectives, finish_objectives, new_objectives,
    normalize_objectives, objective_summary, original_objectives,
    package_objectives, verify_objectives, verify_objectives_package,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_source_to_runtime_checkpoint_replay_export():
    source = original_objectives()
    before = copy.deepcopy(source)
    initial = new_objectives(source)
    first = advance_objectives(initial)
    assert first["state"]["score"] == 10
    assert first["state"]["journal"][0]["outcomes"][0]["status"] == "completed"
    assert first["save"]["parent_digest"] is not None
    finished = finish_objectives(source, resume=first)
    assert finished["state"]["phase"] == "won"
    assert finished["state"]["score"] == 30
    assert finished == finish_objectives(source)
    assert source == before
    assert verify_objectives(json.loads(json.dumps(finished))) == finished
    package = package_objectives(first)
    assert verify_objectives_package(json.loads(json.dumps(package))) == package
    assert finish_objectives(source, resume=package["snapshot"]) == finished


def test_objective_summary_exposes_pending_and_completed():
    started = new_objectives(original_objectives())
    assert [x["status"] for x in objective_summary(started)["objectives"]] == [
        "pending", "pending",
    ]
    first = advance_objectives(started)
    assert [x["status"] for x in objective_summary(first)["objectives"]] == [
        "completed", "pending",
    ]


def test_currency_condition_only_reads_canonical_earned_currency():
    source = original_objectives()
    source["objectives"][1] = {
        "objective_id": "treasury", "encounter_id": "tide_gate",
        "kind": "currency", "threshold": 31, "points": 50,
        "requires": ["clear_reeds"],
    }
    result = finish_objectives(source)
    assert result["state"]["score"] == 10
    assert result["state"]["journal"][-1]["outcomes"][0]["status"] == "failed"
    source["objectives"][1]["threshold"] = 30
    assert finish_objectives(source)["state"]["score"] == 60


def test_forward_dependencies_and_unknown_encounters_fail_closed():
    source = original_objectives()
    source["objectives"][0]["requires"] = ["guard_lantern"]
    with pytest.raises(CombatSessionError, match="forward"):
        normalize_objectives(source)
    source = original_objectives()
    source["objectives"][1]["encounter_id"] = "missing"
    with pytest.raises(CombatSessionError, match="unknown encounter"):
        new_objectives(source)


@pytest.mark.parametrize("edit", [
    lambda s: s["objectives"][1].update(objective_id="clear_reeds"),
    lambda s: s["objectives"][1].update(kind="python"),
    lambda s: s["objectives"][1].update(threshold=True),
    lambda s: s["objectives"][1].update(points=10001),
    lambda s: s["objectives"][1].update(requires=["clear_reeds", "clear_reeds"]),
    lambda s: s["objectives"][1].update(requires=["guard_lantern"]),
    lambda s: s["objectives"][0].update(kind="final_victory"),
    lambda s: s["objectives"][0].update(points=-1),
    lambda s: s.update(schema_version="wrong"),
    lambda s: s.update(objectives=[]),
    lambda s: s["objectives"][0].update(unknown=1),
])
def test_malformed_objectives_are_rejected(edit):
    source = original_objectives()
    edit(source)
    with pytest.raises(CombatSessionError):
        new_objectives(source)


@pytest.mark.parametrize("edit", [
    lambda s: s["state"].update(score=9999),
    lambda s: s["state"]["journal"][0]["outcomes"][0].update(points=9999),
    lambda s: s["campaign_session"]["state"].update(currency=9999),
    lambda s: s["save"].update(parent_digest="0" * 64),
    lambda s: s.update(state_digest="0" * 64),
    lambda s: s["source"]["objectives"][0].update(points=9999),
    lambda s: s["state"]["journal"][0].update(combat_digest="0" * 64),
])
def test_tampered_nested_state_and_rewards_fail_closed(edit):
    snapshot = advance_objectives(new_objectives(original_objectives()))
    corrupted = copy.deepcopy(snapshot)
    edit(corrupted)
    with pytest.raises(CombatSessionError):
        verify_objectives(corrupted)


def test_reject_resume_with_different_authored_source():
    original = original_objectives()
    checkpoint = advance_objectives(new_objectives(original))
    changed = copy.deepcopy(original)
    changed["objectives"][0]["points"] = 9
    with pytest.raises(CombatSessionError, match="source mismatch"):
        finish_objectives(changed, resume=checkpoint)


def test_cannot_advance_terminal_checkpoint():
    finished = finish_objectives(original_objectives())
    with pytest.raises(CombatSessionError, match="terminal"):
        advance_objectives(finished)


def test_package_manifest_and_receipt_are_not_authority():
    package = package_objectives(finish_objectives(original_objectives()))
    for key, value in (("score", 999), ("phase", "active")):
        tampered = copy.deepcopy(package)
        tampered["manifest"][key] = value
        with pytest.raises(CombatSessionError):
            verify_objectives_package(tampered)
    tampered = copy.deepcopy(package)
    tampered["digest"] = "0" * 64
    with pytest.raises(CombatSessionError):
        verify_objectives_package(tampered)


def test_cli_end_to_end_with_replay_and_portable_package(capsys):
    source = original_objectives()
    assert main(["combat-objectives", "start", "--source-json", json.dumps(source)]) == 0
    start = json.loads(capsys.readouterr().out)
    assert main(["combat-objectives", "advance", "--session-json", json.dumps(start)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["combat-objectives", "finish", "--session-json", json.dumps(first)]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["state"]["score"] == 30
    assert main(["combat-objectives", "pack", "--session-json", json.dumps(final)]) == 0
    portable = json.loads(capsys.readouterr().out)
    assert main(["combat-objectives", "unpack", "--package-json", json.dumps(portable)]) == 0
    assert json.loads(capsys.readouterr().out) == portable
    assert main(["combat-objectives", "summary", "--session-json", json.dumps(final)]) == 0
    assert json.loads(capsys.readouterr().out)["score"] == 30


def test_cli_strict_json_and_schema_failure(capsys):
    assert main(["combat-objectives", "start", "--source-json", '{"a":1,"a":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert main(["combat-objectives", "start", "--source-json",
                 json.dumps({"schema_version": SCHEMA, "campaign": original_campaign(),
                             "objectives": []})]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
