"""Regression: stale menu selections must never overwrite another player's save."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_concurrent_menu_selection_reloads_authoritative_revision(tmp_path):
    root = tmp_path / "saves"
    first = SlotStore(root)
    initial = first.new("journey")
    assert initial["actions"]
    output = []
    invoked = False

    def concurrent_choice(_prompt):
        nonlocal invoked
        if invoked:
            return "q"
        invoked = True
        # The menu was rendered at revision zero. Another independent
        # connection commits its turn before the first player's response.
        rival = SlotStore(root)
        rival.step("journey", initial["actions"][0], expected_head=initial["head"])
        return "0"

    final = play(first, "journey", read=concurrent_choice, write=output.append)
    authoritative = SlotStore(root).load("journey")
    assert final["head"] == authoritative["head"]
    assert final["revision"] == authoritative["revision"] == 1
    assert SlotStore(root).audit("journey")["verified"] is True
    assert any("Action not saved; refreshing authoritative slot" in line for line in output)
