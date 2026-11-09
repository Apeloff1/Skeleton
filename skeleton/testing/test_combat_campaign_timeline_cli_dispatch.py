"""Import and dispatch must remain valid after combat CLI additions."""
from __future__ import annotations

import importlib

from skeleton.__main__ import main


def test_combat_campaign_timeline_dispatch_is_real(monkeypatch):
    module = importlib.import_module(
        "skeleton.game.gameplay.combat_campaign_timeline"
    )
    received = []

    def stub(argv):
        received.append(argv)
        return 41

    monkeypatch.setattr(module, "cli", stub)
    assert main(["combat-campaign-timeline", "probe"]) == 41
    assert received == [["probe"]]


def test_combat_campaign_timeline_help_is_in_docstring(capsys):
    assert main(["help"]) == 0
    assert "combat-campaign-timeline  Audit player turns" in capsys.readouterr().out
