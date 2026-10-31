"""Canonical tactical player choices through expedition save and CLI."""
from __future__ import annotations

import copy
import io
import json

import pytest

from skeleton.game.gameplay.arena_bundle import export_bundle, import_bundle
from skeleton.game.gameplay.arena_expedition import (
    cli, original_expedition, resume_expedition, simulate_expedition,
    verify_expedition,
)
from skeleton.game.gameplay.arena_expedition_interactive import play_expedition
from skeleton.game.gameplay.arena_player_policy import run_player_tactics
from skeleton.game.gameplay.arena_policy import run_autoplay
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _script(arena, hero="scout"):
    reference = run_autoplay(arena)
    return [
        event["action"] for event in reference["journal"]
        if event["action"]["actor_id"] == hero
    ]


def _first():
    source = original_expedition()
    return source, source["arenas"][0]["arena"]


def test_player_tactics_matches_canonical_opponent_policy_and_replay():
    source, arena = _first()
    actions = _script(arena)
    assert actions
    actual = run_player_tactics(arena, source["hero_id"], actions)
    assert actual == run_autoplay(arena)
    assert actual["state"]["phase"] == "won"


def test_manual_expedition_choices_round_trip_save_bundle_and_resume():
    source, arena = _first()
    first_action = {"kind": "fight_tactical", "hero_actions": _script(arena)}
    first = simulate_expedition(source, [first_action])
    assert first["state"]["next_index"] == 1
    assert first["state"]["currency"] == 10
    assert first["journal"][0]["action"] == first_action
    bundle = export_bundle(first)
    assert import_bundle(json.loads(json.dumps(bundle))) == first
    resumed = resume_expedition(import_bundle(bundle), [{"kind": "fight"}])
    assert resumed["state"]["phase"] == "won"
    assert verify_expedition(json.loads(json.dumps(resumed))) == resumed


@pytest.mark.parametrize("change", [
    lambda action: action["hero_actions"].append(
        {"kind": "guard", "actor_id": "scout"}
    ),
    lambda action: action.update(hero_actions=[]),
    lambda action: action.update(hero_actions=[
        {"kind": "guard", "actor_id": "warden"}
    ]),
    lambda action: action.update(hero_actions=[
        {"kind": "move", "actor_id": "scout", "direction": "invalid"}
    ]),
    lambda action: action.update(hero_actions=[{}] * 65),
    lambda action: action.update(hero_actions="guard"),
])
def test_tactical_script_fails_closed_without_earning_reward(change):
    source, arena = _first()
    action = {"kind": "fight_tactical", "hero_actions": _script(arena)}
    change(action)
    with pytest.raises(CombatSessionError):
        simulate_expedition(source, [action])


def test_tampered_manual_action_journal_cannot_rewrite_reward():
    source, arena = _first()
    saved = simulate_expedition(
        source, [{"kind": "fight_tactical", "hero_actions": _script(arena)}],
    )
    forged = copy.deepcopy(saved)
    forged["journal"][0]["action"]["hero_actions"][0]["kind"] = "guard"
    with pytest.raises(CombatSessionError):
        verify_expedition(forged)


def test_interactive_expedition_accepts_manual_tactics_and_finishes():
    source, arena = _first()
    actions = [
        {"kind": "fight_tactical", "hero_actions": _script(arena)},
        {"kind": "fight"},
    ]
    input_stream = io.StringIO("".join(json.dumps(a) + "\n" for a in actions))
    output_stream = io.StringIO()
    saved = play_expedition(
        source, input_stream=input_stream, output_stream=output_stream,
    )
    events = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert saved["state"]["phase"] == "won"
    assert [e["event"] for e in events] == [
        "turn", "accepted", "turn", "accepted", "terminal",
    ]
    assert events[-1]["session"] == saved


def test_interactive_invalid_input_preserves_checkpoint_then_recovers():
    source, _ = _first()
    reader = io.StringIO('{"kind":"buy","item_id":"tide_tonic"}\n'
                         '{"kind":"fight"}\n{"kind":"fight"}\n')
    writer = io.StringIO()
    result = play_expedition(source, input_stream=reader, output_stream=writer)
    events = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert events[1]["event"] == "rejected"
    assert events[1]["state_digest"] == events[0]["state_digest"]
    assert result["state"]["phase"] == "won"


def test_interactive_eof_and_wrong_source_fail_closed():
    source, _ = _first()
    with pytest.raises(CombatSessionError, match="input ended"):
        play_expedition(source, input_stream=io.StringIO(), output_stream=io.StringIO())
    first = simulate_expedition(source, [{"kind": "fight"}])
    changed = copy.deepcopy(source)
    changed["expedition_id"] = "changed"
    with pytest.raises(CombatSessionError, match="source mismatch"):
        play_expedition(
            changed, resume=first, input_stream=io.StringIO(),
            output_stream=io.StringIO(),
        )


def test_cli_manual_tactical_simulate_and_replay(capsys):
    source, arena = _first()
    actions = [{"kind": "fight_tactical", "hero_actions": _script(arena)}]
    assert cli([
        "simulate", "--source-json", json.dumps(source),
        "--actions-json", json.dumps(actions),
    ]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["currency"] == 10
    assert cli(["verify", "--session-json", json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
