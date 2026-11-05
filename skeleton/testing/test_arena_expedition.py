"""Offline expedition integration: real combat, currency, inventory, replay."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import verify_arena
from skeleton.game.gameplay.arena_expedition import (
    _advance, cli, new_expedition, normalize_expedition,
    original_expedition, resume_expedition, simulate_expedition,
    verify_expedition,
)


def test_original_campaign_is_source_bound_and_earns_rewards():
    source = original_expedition()
    result = simulate_expedition(source, [
        {"kind": "fight"}, {"kind": "buy", "item_id": "tide_tonic"},
        {"kind": "use", "item_id": "tide_tonic"}, {"kind": "fight"},
    ])
    assert result["state"]["phase"] == "won"
    assert result["state"]["next_index"] == 2
    assert result["state"]["currency"] == 25
    assert result["state"]["purchased"] == {"tide_tonic": 1}
    assert result["state"]["inventory"] == {}
    assert [x["reward"] for x in result["state"]["arenas"]] == [10, 20]
    for encounter in result["state"]["arenas"]:
        assert verify_arena(encounter["session"]) == encounter["session"]
    assert verify_expedition(json.loads(json.dumps(result))) == result


def test_save_resume_after_first_fight_matches_one_pass():
    source = original_expedition()
    first = simulate_expedition(source, [{"kind": "fight"}])
    assert first["state"]["phase"] == "active"
    continued = resume_expedition(json.loads(json.dumps(first)), [
        {"kind": "buy", "item_id": "tide_tonic"},
        {"kind": "use", "item_id": "tide_tonic"},
        {"kind": "fight"},
    ])
    assert continued == simulate_expedition(source, [
        {"kind": "fight"}, {"kind": "buy", "item_id": "tide_tonic"},
        {"kind": "use", "item_id": "tide_tonic"}, {"kind": "fight"},
    ])
    assert first["state"]["currency"] == 10


def test_no_free_items_and_no_double_reward():
    source = original_expedition()
    session = new_expedition(source)
    with pytest.raises(CombatSessionError, match="insufficient"):
        _advance(session, {"kind": "buy", "item_id": "tide_tonic"})
    with pytest.raises(CombatSessionError, match="not owned"):
        _advance(session, {"kind": "use", "item_id": "tide_tonic"})
    first = _advance(session, {"kind": "fight"})
    assert first["state"]["currency"] == 10
    with pytest.raises(CombatSessionError, match="not owned"):
        _advance(first, {"kind": "use", "item_id": "tide_tonic"})


def test_shop_stock_and_inventory_are_bounded():
    source = original_expedition()
    source["shop"][0]["price"] = 1
    source["shop"][0]["stock"] = 1
    session = _advance(new_expedition(source), {"kind": "fight"})
    bought = _advance(session, {"kind": "buy", "item_id": "tide_tonic"})
    with pytest.raises(CombatSessionError, match="stock exhausted"):
        _advance(bought, {"kind": "buy", "item_id": "tide_tonic"})
    assert bought["state"]["currency"] == session["state"]["currency"] - 1


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(world_id="other"),
    lambda x: x["arenas"][0].update(reward=-1),
    lambda x: x["arenas"][1]["arena"].update(arena_id="canal_watch"),
    lambda x: x["arenas"][1]["arena"]["actors"][0].update(attack=99),
    lambda x: x["arenas"][0]["arena"].update(turn_limit=65),
    lambda x: x["shop"][0].update(price=0),
    lambda x: x["shop"][0].update(stock=True),
    lambda x: x["shop"].append(x["shop"][0]),
    lambda x: x.update(schema_version="future"),
    lambda x: x["arenas"].append(x["arenas"][0]),
])
def test_bad_authored_campaign_fails_closed(mutate):
    source = original_expedition()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_expedition(source)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"].update(currency=100000),
    lambda x: x["state"].update(hero_hp=999),
    lambda x: x["state"]["arenas"][0].update(reward=1000),
    lambda x: x["state"]["arenas"][0]["session"]["state"].update(tick=0),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x["journal"].append(x["journal"][0]),
])
def test_forged_reward_save_and_journal_rejected(mutate):
    saved = simulate_expedition(original_expedition(), [{"kind": "fight"}])
    bad = copy.deepcopy(saved)
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_expedition(bad)


def test_terminal_game_cannot_farm_reward():
    source = original_expedition()
    finished = simulate_expedition(source, [
        {"kind": "fight"}, {"kind": "fight"},
    ])
    assert finished["state"]["phase"] == "won"
    with pytest.raises(CombatSessionError, match="terminal"):
        _advance(finished, {"kind": "fight"})


def test_cli_demo_verify_and_invalid_source(capsys):
    assert cli(["demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["verify", "--session-json", json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"bad":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_main_cli_reaches_actual_expedition(capsys):
    from skeleton.__main__ import main
    assert main(["combat-expedition", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["phase"] == "won"
