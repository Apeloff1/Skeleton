"""Typed offline quest editor, provenance, optimistic leases and previews."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    demo_actions, normalize_quest, original_quest, simulate_quest,
)
from skeleton.game.gameplay.expedition_quest_author import (
    apply_edits, cli, original_edit_demo, save_compatibility, verify_edits,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_real_authoring_change_replays_and_remains_playable():
    receipt = original_edit_demo()
    assert receipt["before_digest"] != receipt["source_digest"]
    assert receipt["source"]["npcs"][0]["gift"] == "copper"
    assert receipt["source"]["recipes"][0]["inputs"] == ["copper", "ore"]
    assert verify_edits(json.loads(json.dumps(receipt))) == receipt
    played = simulate_quest(receipt["source"], demo_actions())
    assert played["state"]["phase"] == "finished"
    assert played["state"]["ending"] == "beacon_lit"
    assert played["state"]["items"] == {"signal_beacon": 1}


def test_edited_source_preview_is_replayed_from_canonical_runtime():
    source = original_quest()
    receipt = apply_edits(
        source, [{"op": "set_npc_gift", "id": "guide", "value": "copper"},
                {"op": "set_recipe_inputs", "id": "beacon",
                 "value": ["copper", "ore"]}],
        expected_digest=dig(normalize_quest(source)),
        preview_actions=demo_actions(),
    )
    assert receipt["preview"]["state"]["phase"] == "finished"
    assert verify_edits(receipt) == receipt


def test_save_is_not_silently_transplanted_across_source_edits():
    original = original_quest()
    saved = simulate_quest(original, demo_actions())
    receipt = original_edit_demo()
    result = save_compatibility(receipt, saved)
    assert result["compatible"] is False
    assert result["action"] == "restart_from_new_source"
    assert result["old_source_digest"] != result["edited_source_digest"]


@pytest.mark.parametrize("ops,pattern", [
    ([{"op": "set_npc_gift", "id": "missing", "value": "ore"}], "missing"),
    ([{"op": "add_npc", "value": {"id": "guide", "route": ["dock"],
                                 "gift": "copper"}}], "already exists"),
    ([{"op": "remove_location", "id": "dock"}], "location"),
    ([{"op": "set_recipe_inputs", "id": "beacon",
       "value": ["unearned"]}], "recipe inputs"),
    ([{"op": "set_npc_gift", "id": "guide",
       "value": "../escape"}], "invalid"),
    ([{"op": "set_npc_route", "id": "guide",
       "value": ["missing"]}], "NPC route"),
    ([{"op": "script", "value": "eval()"}], "unsupported"),
])
def test_unsafe_or_invalid_authoring_fails_closed(ops, pattern):
    source = original_quest()
    with pytest.raises(CombatSessionError, match=pattern):
        apply_edits(source, ops, expected_digest=dig(normalize_quest(source)))


def test_optimistic_digest_fence_and_noop_detection():
    source = original_quest()
    with pytest.raises(CombatSessionError, match="optimistic digest"):
        apply_edits(source, [{"op": "set_npc_gift", "id": "guide",
                              "value": "copper"}], expected_digest="0" * 64)
    with pytest.raises(CombatSessionError, match="no source change"):
        apply_edits(source, [{"op": "set_npc_gift", "id": "guide",
                              "value": "reed"}],
                    expected_digest=dig(normalize_quest(source)))


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x["source"]["npcs"][0].update(gift="gold"),
    lambda x: x["operations"][0].update(value="gold"),
    lambda x: x.update(operations_digest="0" * 64),
    lambda x: x["base_source"]["npcs"][0].update(gift="gold"),
    lambda x: x.update(before_digest="0" * 64),
])
def test_forged_editor_receipt_rejected(mutate):
    bad = copy.deepcopy(original_edit_demo())
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_edits(bad)


def test_atomic_multi_operation_edit_can_fix_transient_invalid_source():
    source = original_quest()
    receipt = apply_edits(source, [
        {"op": "set_npc_gift", "id": "guide", "value": "copper"},
        {"op": "set_recipe_inputs", "id": "beacon", "value": ["copper", "ore"]},
    ], expected_digest=dig(normalize_quest(source)))
    assert receipt["source"]["recipes"][0]["inputs"] == ["copper", "ore"]


def test_authoring_batch_bounded_and_strict():
    source = original_quest()
    expected = dig(normalize_quest(source))
    with pytest.raises(CombatSessionError, match="batch"):
        apply_edits(source, [], expected_digest=expected)
    with pytest.raises(CombatSessionError, match="batch"):
        apply_edits(source, [{"op": "set_start", "value": "dock"}] * 49,
                    expected_digest=expected)
    with pytest.raises(CombatSessionError):
        apply_edits(source, [{"op": "set_start", "value": "dock",
                              "unsafe": True}], expected_digest=expected)


def test_installed_quest_author_cli(capsys):
    from skeleton.__main__ import main
    assert main(["quest-author", "demo"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_digest"] != receipt["before_digest"]
    assert cli(["verify", "--receipt-json", json.dumps(receipt)]) == 0
    assert json.loads(capsys.readouterr().out) == receipt
    assert cli(["edit", "--source-json", '{"bad":true}',
                "--operations-json", "[]", "--expected-digest", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
