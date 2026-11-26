"""Two consumer processes must never apply an action from a stale menu.

The competing process commits while the first player's input is outstanding.
The interactive loop must reload the authoritative revision, not replay the
stale menu selection against the new world state.
"""
from pathlib import Path

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_concurrent_menu_stale_action_is_rejected_and_refreshed(tmp_path: Path):
    root = tmp_path / "private-save"
    first = SlotStore(root)
    second = SlotStore(root)
    initial = first.new("race")
    assert initial["status"] == "playing"
    assert initial["actions"]

    output = []
    entered = False

    def read(_prompt):
        nonlocal entered
        if not entered:
            entered = True
            # Another consumer advances the same slot while the first
            # consumer is looking at its old action list.
            committed = second.step(
                "race", initial["actions"][0], expected_head=initial["head"]
            )
            assert committed["revision"] == 1
            return "0"
        return "q"

    final = play(first, "race", read=read, write=output.append, ascii_mode=True)
    reopened = SlotStore(root).load("race")
    assert final["revision"] == reopened["revision"] == 1
    assert final["head"] == reopened["head"]
    assert final["head"] != initial["head"]
    assert any("refreshing authoritative slot" in line for line in output)
    assert all(line.isascii() for line in output)


def test_stale_head_cannot_mutate_even_with_current_valid_action(tmp_path: Path):
    store = SlotStore(tmp_path / "private-save")
    initial = store.new("cas")
    advanced = store.step("cas", initial["actions"][0], expected_head=initial["head"])
    from skeleton.game.gameplay.ridge_rescue.consumer_store import StoreError
    import pytest

    with pytest.raises(StoreError, match="stale save revision"):
        store.step("cas", advanced["actions"][0], expected_head=initial["head"])
    reopened = SlotStore(tmp_path / "private-save").load("cas")
    assert reopened["revision"] == 1
    assert reopened["head"] == advanced["head"]
