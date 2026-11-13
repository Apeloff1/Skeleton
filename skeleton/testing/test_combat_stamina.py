"""End-to-end stamina resource, canonical combat, replay and export tests."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.combat_stamina import (
    _step, cli, edit_stamina, export_stamina, import_stamina,
    legal_stamina_actions, new_stamina, normalize_stamina,
    original_stamina, resume_stamina, simulate_stamina, verify_stamina,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_combat_earns_victory_and_portable_replay():
    source, actions = original_stamina()
    final = simulate_stamina(source, actions)
    assert final["state"]["phase"] == "won"
    assert final["state"]["winner"] == "wayfarers"
    assert final["state"]["stamina"]["scout"] == 0
    assert final["state"]["combat"]["state"]["actors"]["warden"]["hp"] == 0
    assert verify_stamina(final) == final
    assert import_stamina(export_stamina(final)) == final


def test_save_resume_exactly_matches_uninterrupted_play():
    source, actions = original_stamina()
    partial = simulate_stamina(source, actions[:2])
    assert resume_stamina(import_stamina(export_stamina(partial)), actions[2:]) == simulate_stamina(source, actions)


def test_exhaustion_blocks_attack_and_rest_restores_energy():
    source, _ = original_stamina()
    for actor in source["scenario"]["actors"]:
        if actor["id"] == "scout":
            actor["attack"] = 1
        else:
            actor["max_hp"] = 100
    session = new_stamina(source)
    for action in [
        {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
        {"kind": "rest", "actor_id": "warden"},
        {"kind": "attack", "actor_id": "scout", "target_id": "warden"},
        {"kind": "rest", "actor_id": "warden"},
    ]:
        session = _step(session, action)
    assert not any(a["kind"] == "attack" for a in legal_stamina_actions(session))
    with pytest.raises(CombatSessionError, match="insufficient stamina"):
        _step(session, {"kind": "attack", "actor_id": "scout", "target_id": "warden"})
    recovered = _step(session, {"kind": "rest", "actor_id": "scout"})
    assert recovered["state"]["stamina"]["scout"] == 3
    assert verify_stamina(session) == session


@pytest.mark.parametrize("change", [
    {"max_stamina": 0}, {"max_stamina": True}, {"attack_cost": 99},
    {"guard_cost": -1}, {"rest_gain": 0}, {"player_team": "unknown"},
    {"schema_version": "future"},
])
def test_invalid_source_fails_closed(change):
    source, _ = original_stamina()
    source.update(change)
    with pytest.raises(CombatSessionError):
        normalize_stamina(source)


@pytest.mark.parametrize("field", ["state", "journal", "save", "source_digest", "event_bus_digest"])
def test_forged_session_rejected(field):
    source, actions = original_stamina()
    bad = copy.deepcopy(simulate_stamina(source, actions[:2]))
    if field == "state":
        bad["state"]["stamina"]["scout"] = 99
    elif field == "journal":
        bad["journal"][0]["receipt"] = "0" * 64
    elif field == "save":
        bad["save"]["tick"] = 999
    else:
        bad[field] = "0" * 64
    with pytest.raises(CombatSessionError):
        verify_stamina(bad)


def test_recomputed_bundle_checksum_cannot_forge_combat_state():
    source, actions = original_stamina()
    bundle = export_stamina(simulate_stamina(source, actions))
    bundle["session"]["state"]["stamina"]["scout"] = 999
    bundle["checksum"] = dig({k: v for k, v in bundle.items() if k != "checksum"})
    with pytest.raises(CombatSessionError):
        import_stamina(bundle)


def test_authoring_is_transactional_and_source_digest_fenced():
    source, actions = original_stamina()
    old = normalize_stamina(source)
    authored = edit_stamina(source, dig(old), [
        {"field": "max_stamina", "value": 6},
        {"field": "attack_cost", "value": 3},
    ], actions)
    assert authored["source"]["max_stamina"] == 6
    assert authored["preview"]["state"]["phase"] == "won"
    assert source["max_stamina"] == 4
    with pytest.raises(CombatSessionError, match="conflict"):
        edit_stamina(source, "0" * 64, [])
    with pytest.raises(CombatSessionError):
        edit_stamina(source, dig(old), [{"field": "attack_cost", "value": 99}])


def test_cli_dispatch_gameplay_save_export_and_reject(capsys):
    from skeleton.__main__ import main
    assert main(["combat-stamina", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}', "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
