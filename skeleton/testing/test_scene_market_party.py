"""Cooperative market vertical: real economy, role-gated turns and portable replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_party import (
    _advance, accept_party, export_party, import_party, new_party,
    normalize_party, original_party, resume_party, simulate_party, verify_party,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_party_is_winnable_with_earned_goods():
    source, turns = original_party()
    session = simulate_party(source, turns)
    market = session["state"]["market"]["state"]
    assert market["phase"] == "won"
    assert market["credits"] == 1
    assert market["goods"] == {}
    assert market["purchases"] == {"copper_badge": 1}
    assert market["delivered"] == ["sanctuary_seal"]
    assert sum(x["merchant"] for x in session["state"]["contributions"].values()) == 1
    assert sum(x["artisan"] for x in session["state"]["contributions"].values()) == 1
    assert sum(x["courier"] for x in session["state"]["contributions"].values()) == 1
    assert verify_party(json.loads(json.dumps(session))) == session
    assert import_party(json.loads(json.dumps(export_party(session)))) == session
    assert accept_party(source, turns)["phase"] == "won"


@pytest.mark.parametrize("split", [0, 1, 2, 5, 7, 9, 12])
def test_resume_at_any_turn_boundary(split):
    source, turns = original_party()
    split = min(split, len(turns))
    saved = simulate_party(source, turns[:split])
    assert resume_party(json.loads(json.dumps(saved)), turns[split:]) == (
        simulate_party(source, turns))


def test_wrong_player_and_missing_role_fail_closed():
    source, _ = original_party()
    session = new_party(source)
    with pytest.raises(SceneTravelError, match="not this player"):
        _advance(session, {"player_id": "mira", "action": {"kind": "pass"}})
    with pytest.raises(SceneTravelError, match="lacks role"):
        _advance(session, {"player_id": "rowan",
                           "action": {"kind": "craft", "recipe_id": "seal_press"}})
    assert session == new_party(source)


def test_market_ownership_cannot_be_bypassed():
    source, _ = original_party()
    start = new_party(source)
    with pytest.raises(SceneTravelError):
        _advance(start, {"player_id": "rowan",
                         "action": {"kind": "buy", "offer_id": "copper_badge"}})
    with pytest.raises(SceneTravelError):
        _advance(start, {"player_id": "rowan",
                         "action": {"kind": "tile", "action": {
                             "kind": "move", "direction": "invalid"}}})
    assert start["state"]["market"]["state"]["credits"] == 0


def test_pass_advances_turn_but_not_market_economy():
    source, _ = original_party()
    start = new_party(source)
    after = _advance(start, {"player_id": "rowan", "action": {"kind": "pass"}})
    assert after["state"]["market"] == start["state"]["market"]
    assert after["state"]["sequence"] == 1
    assert after["state"]["passes"]["rowan"] == 1
    assert after["state"]["turn_index"] == 1
    assert after["state"]["contributions"] == start["state"]["contributions"]


@pytest.mark.parametrize("mutation", [
    lambda s: s["players"].append(s["players"][0]),
    lambda s: s["players"][0].update(roles=["navigator", "navigator"]),
    lambda s: s["players"][0].update(roles=["admin"]),
    lambda s: s["players"][2].update(roles=[]),
    lambda s: s["players"][0].update(player_id="../bad"),
    lambda s: s.update(schema_version="future"),
])
def test_bad_party_source_rejected(mutation):
    source, _ = original_party()
    mutation(source)
    with pytest.raises(SceneTravelError):
        normalize_party(source)


@pytest.mark.parametrize("mutation", [
    lambda s: s["state"]["market"]["state"].update(credits=999),
    lambda s: s["state"]["contributions"]["rowan"].update(merchant=999),
    lambda s: s["state"]["passes"].update(rowan=999),
    lambda s: s["state"].update(turn_index=(s["state"]["turn_index"] + 1) % 3),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["save"].update(sequence=0),
    lambda s: s.update(source_digest="0" * 64),
])
def test_forged_party_checkpoint_rejected(mutation):
    source, turns = original_party()
    forged = copy.deepcopy(simulate_party(source, turns))
    mutation(forged)
    with pytest.raises(SceneTravelError):
        verify_party(forged)


def test_party_bundle_forgery_and_future_version_rejected():
    source, turns = original_party()
    bundle = export_party(simulate_party(source, turns))
    for key in ("checksum", "state_digest", "source_digest"):
        forged = copy.deepcopy(bundle)
        forged[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_party(forged)
    forged = copy.deepcopy(bundle)
    forged["schema_version"] = "future"
    with pytest.raises(SceneTravelError):
        import_party(forged)


def test_batch_rejection_is_transactional():
    source, turns = original_party()
    checkpoint = simulate_party(source, turns[:3])
    before = copy.deepcopy(checkpoint)
    with pytest.raises(SceneTravelError):
        resume_party(checkpoint, [
            turns[3], {"player_id": "forged", "action": {"kind": "pass"}},
        ])
    assert checkpoint == before


def test_cli_demo_and_accept_are_user_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party", "demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["state"]["market"]["state"]["phase"] == "won"
    assert main(["scene-market-party", "accept"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["phase"] == "won"
    assert receipt["export_checksum"]


def test_caller_cannot_mutate_accepted_party_action_after_commit():
    source, _ = original_party()
    session = new_party(source)
    action = {"kind": "tile", "action": {"kind": "move", "direction": "east"}}
    try:
        updated = _advance(session, {"player_id": "rowan", "action": action})
    except SceneTravelError:
        # The original authored map may disallow east from its spawn.
        action["action"]["direction"] = "south"
        updated = _advance(session, {"player_id": "rowan", "action": action})
    snapshot = copy.deepcopy(updated)
    action["action"]["direction"] = "forged"
    assert updated == snapshot
    assert verify_party(updated) == updated
