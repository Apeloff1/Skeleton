"""Canonical entry-point dispatch for cooperative market gameplay.

These tests verify user-reachable CLI routes without invoking external providers
or relying on a live game session. The actual gameplay acceptance lives in the
market party engine's focused tests.
"""
from __future__ import annotations

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay import (
    scene_market_party,
    scene_market_party_author,
    scene_market_party_board,
    scene_market_party_interactive,
)


_COMMAND_MODULES = {
    "scene-market-party": scene_market_party,
    "scene-market-party-author": scene_market_party_author,
    "scene-market-party-board": scene_market_party_board,
    "scene-market-party-play": scene_market_party_interactive,
}


@pytest.mark.parametrize("command", tuple(_COMMAND_MODULES))
def test_cooperative_market_commands_dispatch_to_real_cli(monkeypatch, command):
    module = _COMMAND_MODULES[command]
    received = []

    def cli(args):
        received.append(args)
        return 37

    monkeypatch.setattr(module, "cli", cli)
    assert main([command, "probe", "--token", "original"]) == 37
    assert received == [["probe", "--token", "original"]]


def test_cooperative_market_help_is_discoverable(capsys):
    assert main(["help"]) == 0
    output = capsys.readouterr().out
    for command in (
        "scene-market-party", "scene-market-party-author",
        "scene-market-party-board", "scene-market-party-play",
    ):
        assert command in output
