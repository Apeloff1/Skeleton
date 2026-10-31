"""End-user offline combat: actual FLGB events, deterministic damage, saves and CLI."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.app.combat_cli import main as run_combat_cli
from skeleton.game.gameplay.combat_logic import (
    CombatSessionError, advance, replay, validate_source, verify_save,
)
from skeleton.game.gameplay.encounter_session import MAX_TURNS

FIXTURE = Path(__file__).parent / "fixtures" / "combat_original_lantern_harbor.json"


@pytest.fixture
def source():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def attack():
    return {"action": "attack", "attack_id": "lantern-jab"}


def test_canonical_source_and_offline_determinism(source):
    initial = replay(source, [])
    assert initial["state"]["turn"] == 0
    assert initial["state"]["phase"] == "active"
    assert initial["state"]["player"]["hp"] == 100
    assert initial["state"]["enemy"]["hp"] == 72
    assert initial["event_digest"]
    commands = [attack()] * 6
    a = replay(source, commands)
    b = replay(deepcopy(source), deepcopy(commands))
    assert a == b
    assert a["state"]["phase"] == "victory"
    assert a["state"]["reward"] == "saltwind-map-fragment"
    assert a["state"]["enemy"]["hp"] == 0
    assert a["terminal"] is True
    assert verify_save(source, a) == a
    assert a["save_metadata_digest"] != initial["save_metadata_digest"]
    assert len(a["trace"]) >= 6


def test_incremental_save_reopen_and_source_binding(source):
    first = advance(source, None, attack())
    assert first["state"]["turn"] == 1
    second = advance(source, first, {"action": "guard"})
    assert second == replay(source, [attack(), {"action": "guard"}])
    assert verify_save(source, json.loads(json.dumps(second))) == second
    changed = deepcopy(source)
    changed["enemy"]["armor"] += 1
    with pytest.raises(CombatSessionError, match="does not match"):
        verify_save(changed, second)
    with pytest.raises(CombatSessionError, match="does not match"):
        verify_save(source, {**second, "event_digest": "0" * 64})


def test_no_after_victory_replay_or_forged_reward(source):
    winning = replay(source, [attack()] * 6)
    with pytest.raises(CombatSessionError, match="terminal"):
        advance(source, winning, attack())
    with pytest.raises(CombatSessionError, match="terminal"):
        replay(source, [attack()] * 7)
    forged = deepcopy(winning)
    forged["state"]["reward"] = "rare-unearned-treasure"
    with pytest.raises(CombatSessionError, match="does not match"):
        verify_save(source, forged)


def test_enemy_determinism_and_guard_effect(source):
    baseline = replay(source, [attack(), attack()])
    guarded = replay(source, [{"action": "guard"}, attack()])
    assert guarded["state"]["player"]["hp"] > baseline["state"]["player"]["hp"]
    assert guarded["trace"][0] == {"actor": "player", "action": "guard"}
    assert guarded["trace"][1]["actor"] == "enemy"


def test_heal_consumes_real_inventory_and_caps_hp(source):
    s = deepcopy(source)
    s["player"]["healing_items"] = 1
    healed = replay(s, [{"action": "guard"}, {"action": "heal"}])
    assert healed["state"]["player"]["healing_items"] == 0
    assert healed["state"]["player"]["hp"] <= s["player"]["hp"]
    with pytest.raises(CombatSessionError, match="no healing items"):
        replay(s, [{"action": "heal"}, {"action": "heal"}])


def test_source_rejects_unreadable_threat_and_invalid_authored_data(source):
    bad = deepcopy(source)
    bad["attacks"][1]["windup_ms"] = 1
    with pytest.raises(CombatSessionError, match="unreadable"):
        validate_source(bad)
    bad = deepcopy(source)
    bad["attacks"][0]["channels"] = ["body_anim", "body_anim"]
    with pytest.raises(CombatSessionError, match="invalid attack"):
        validate_source(bad)
    bad = deepcopy(source)
    bad["player"]["hp"] = True
    with pytest.raises(CombatSessionError, match="hp"):
        validate_source(bad)
    bad = deepcopy(source)
    bad["attacks"][0]["power"] = 0
    with pytest.raises(CombatSessionError, match="power"):
        validate_source(bad)
    bad = deepcopy(source)
    bad["enemy"]["attack_ids"] = ["nonexistent"]
    with pytest.raises(CombatSessionError, match="missing attack"):
        validate_source(bad)
    bad = deepcopy(source)
    bad["unreviewed_code"] = "import os"
    with pytest.raises(CombatSessionError, match="fields"):
        validate_source(bad)


def test_command_fails_closed_without_consuming_save(source):
    prior = replay(source, [])
    for invalid in (
        {"action": "attack", "attack_id": "wind-lash"},
        {"action": "attack"},
        {"action": "guard", "attack_id": "lantern-jab"},
        {"action": "teleport"},
        {"action": "rest", "amount": 999},
    ):
        with pytest.raises(CombatSessionError):
            advance(source, prior, invalid)
    assert verify_save(source, prior) == prior


def test_stamina_and_turn_limits_are_bounded(source):
    s = deepcopy(source)
    s["player"]["stamina"] = 1
    with pytest.raises(CombatSessionError, match="insufficient stamina"):
        replay(s, [attack()])
    resting = replay(s, [{"action": "rest"}])
    assert resting["state"]["player"]["stamina"] == 1
    with pytest.raises(CombatSessionError, match="budget"):
        replay(source, [attack()] * (MAX_TURNS + 1))


def test_combat_cli_play_verify_and_reject_symlink(tmp_path, capsys, source):
    source_path = tmp_path / "encounter.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    first = tmp_path / "save1.json"
    args = ["--source", str(source_path),
            "--command", json.dumps(attack()), "--output", str(first)]
    assert run_combat_cli(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    assert printed["turn"] == 1
    assert first.stat().st_mode & 0o777 == 0o600
    assert run_combat_cli([ "--source", str(source_path),
                        "--save", str(first), "--verify"]) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    assert run_combat_cli(args) == 1
    capsys.readouterr()
    alias = tmp_path / "link.json"
    alias.symlink_to(source_path)
    assert run_combat_cli([ "--source", str(alias)]) == 1


def test_cli_rejects_duplicate_keys_and_corrupt_save(tmp_path, capsys, source):
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    out = tmp_path / "save.json"
    assert run_combat_cli([ "--source", str(source_path),
                        "--command", '{"action":"rest","action":"guard"}',
                        "--output", str(out)]) == 1
    assert not out.exists()
    capsys.readouterr()
    corrupted = tmp_path / "corrupt.json"
    corrupted.write_text('{"schema":"broken"}', encoding="utf-8")
    assert run_combat_cli([ "--source", str(source_path),
                        "--save", str(corrupted), "--verify"]) == 1


def test_source_input_cannot_execute_python_or_network(source):
    malicious = deepcopy(source)
    malicious["attacks"][0]["id"] = "__import__('os').system('false')"
    malicious["player"]["attack_ids"][0] = malicious["attacks"][0]["id"]
    # IDs are data; no eval, exec, provider or network dispatch.
    played = replay(malicious, [{"action": "attack", "attack_id": malicious["attacks"][0]["id"]}])
    assert played["state"]["turn"] == 1
