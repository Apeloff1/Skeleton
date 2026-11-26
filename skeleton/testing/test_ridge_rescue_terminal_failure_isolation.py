"""Consumer-facing failure isolation: rejected input cannot consume game turns.

These tests exercise the real terminal callback and persistent SlotStore,
not a mocked campaign. They are intentionally platform-neutral; they do not
constitute Windows-device certification.
"""
from __future__ import annotations

import json

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import (
    MAX_TERMINAL_INPUT,
    _action_index,
    _strict_action_json,
    play,
)
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


@pytest.mark.parametrize("value", [
    "", "-1", "+0", " 0", "0 ", "00x", "1.0", "０", "²", "١",
    "0" * 10000, "0\n1", "0\t1",
])
def test_menu_parser_rejects_ambiguous_or_unbounded_selection(value):
    assert _action_index(value, 3) is None


@pytest.mark.parametrize("payload", [
    '{"type":"move","type":"wait"}',
    '{"type":NaN}',
    '{"type":Infinity}',
    '{"type":-Infinity}',
    '[]',
    'null',
    '"move"',
    '{"type":1e999}',
    '{"type":',
])
def test_json_rejects_invalid_actions_before_store(payload):
    with pytest.raises(ValueError):
        _strict_action_json(payload)


def test_json_action_valid_utf8_object_roundtrip():
    payload = json.dumps({"type": "inspect", "label": "é"}, ensure_ascii=False)
    assert _strict_action_json(payload) == {"type": "inspect", "label": "é"}


def test_terminal_invalid_commands_preserve_slot_and_reopen(tmp_path):
    root = tmp_path / "save"
    before = SlotStore(root).new("adventure")
    commands = iter((
        "9" * (MAX_TERMINAL_INPUT + 1),
        "not-a-command",
        "999999999",
        "q",
    ))
    output = []
    after = play(SlotStore(root), "adventure",
                 read=lambda _: next(commands), write=output.append,
                 ascii_mode=True)
    reopened = SlotStore(root).load("adventure")
    assert after["head"] == reopened["head"] == before["head"]
    assert after["revision"] == reopened["revision"] == 0
    assert SlotStore(root).audit("adventure")["audit_entries"] == 0
    assert sum("Unavailable command; no turn was consumed." in line
               for line in output) == 3


def test_terminal_read_exhaustion_preserves_committed_action(tmp_path):
    root = tmp_path / "save"
    before = SlotStore(root).new("adventure")
    assert before["actions"]
    commands = iter(("0",))
    output = []
    after = play(SlotStore(root), "adventure",
                 read=lambda _: next(commands), write=output.append,
                 ascii_mode=True)
    reopened = SlotStore(root).load("adventure")
    assert after["head"] == reopened["head"]
    assert after["revision"] == reopened["revision"] == 1
    assert after["head"] != before["head"]
    audit = SlotStore(root).audit("adventure")
    assert audit["verified"] and audit["audit_entries"] == 1


def test_terminal_explicit_quit_does_not_create_a_turn(tmp_path):
    root = tmp_path / "save"
    before = SlotStore(root).new("adventure")
    after = play(SlotStore(root), "adventure",
                 read=lambda _: "q", write=lambda _: None,
                 ascii_mode=True)
    assert after["head"] == before["head"]
    assert after["revision"] == 0
    assert SlotStore(root).audit("adventure")["audit_entries"] == 0
