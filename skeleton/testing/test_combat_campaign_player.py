"""Human campaign play, deterministic save/replay and fail-closed export."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_player import (
    _advance, cli, demo_player_campaign, export_player_campaign,
    import_player_campaign, new_player_campaign, play_player_campaign,
    resume_player_campaign, simulate_player_campaign, verify_player_campaign,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_campaign_player_earns_verified_rewards():
    final = demo_player_campaign()
    assert final["state"]["phase"] == "won"
    assert final["state"]["currency"] == 30
    assert [e["reward"] for e in final["state"]["completed"]] == [10, 20]
    assert final["state"]["hero_hp"] > 0
    assert verify_player_campaign(json.loads(json.dumps(final))) == final
    assert import_player_campaign(export_player_campaign(final)) == final


@pytest.mark.parametrize("split", [0, 1, 2, 3])
def test_split_resume_matches_original_play(split):
    final = demo_player_campaign()
    actions = [event["action"] for event in final["journal"]]
    partial = simulate_player_campaign(original_campaign(), actions[:split])
    assert resume_player_campaign(partial, actions[split:]) == final


def test_wrong_turn_cannot_mint_rewards():
    initial = new_player_campaign(original_campaign())
    with pytest.raises(CombatSessionError):
        _advance(initial, {"kind": "attack", "actor_id": "warden",
                           "target_id": "scout"})
    assert initial["state"]["currency"] == 0


@pytest.mark.parametrize("change", [
    lambda x: x["state"].update(currency=999),
    lambda x: x["state"].update(hero_hp=999),
    lambda x: x["state"]["combat"]["state"]["actors"]["scout"].update(hp=999),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["save"].update(player_turns=999),
])
def test_forged_campaign_checkpoint_rejected(change):
    bad = copy.deepcopy(demo_player_campaign())
    change(bad)
    with pytest.raises(CombatSessionError):
        verify_player_campaign(bad)


def test_forged_portable_currency_rejected_even_if_checksum_recomputed():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    forged = copy.deepcopy(export_player_campaign(demo_player_campaign()))
    forged["session"]["state"]["currency"] += 100
    forged["checksum"] = dig({k: v for k, v in forged.items() if k != "checksum"})
    with pytest.raises(CombatSessionError):
        import_player_campaign(forged)


def test_interactive_matches_canonical_demo_and_eof_checkpoint():
    final = demo_player_campaign()
    actions = [e["action"] for e in final["journal"]]
    stream = io.StringIO()
    played = play_player_campaign(
        original_campaign(),
        reader=io.StringIO("\n".join(json.dumps(a) for a in actions) + "\n"),
        writer=stream,
    )
    assert played == final
    assert json.loads(stream.getvalue().splitlines()[-1])["event"] == "terminal"
    stream = io.StringIO()
    with pytest.raises(CombatSessionError, match="checkpoint emitted"):
        play_player_campaign(original_campaign(), reader=io.StringIO(""), writer=stream)
    assert json.loads(stream.getvalue().splitlines()[-1])["event"] == "checkpoint"


def test_cli_is_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["combat-campaign-player", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["currency"] == 30
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved


def test_stream_flushes_verified_checkpoint_before_eof_failure():
    class FlushRecorder(io.StringIO):
        def __init__(self):
            super().__init__()
            self.flush_count = 0

        def flush(self):
            self.flush_count += 1
            return super().flush()

    writer = FlushRecorder()
    with pytest.raises(CombatSessionError, match="checkpoint emitted"):
        play_player_campaign(original_campaign(), reader=io.StringIO(""),
                             writer=writer)
    assert writer.flush_count >= 2
    assert json.loads(writer.getvalue().splitlines()[-1])["event"] == "checkpoint"
