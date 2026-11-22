"""Real terminal concurrency regression: stale numbered choices must not replay.

The second session commits at the prompt boundary. The first session must
refresh its view rather than applying an action chosen from an obsolete menu.
"""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_stale_numbered_choice_refreshes_without_double_commit(tmp_path):
    root = tmp_path / "saves"
    original = SlotStore(root).new("adventure")
    assert original["actions"]
    messages = []
    prompted = [0]
    external = [None]

    def choose(_prompt: str) -> str:
        prompted[0] += 1
        if prompted[0] == 1:
            # Simulate a separate process committing after the terminal
            # rendered its menu but before the user selected an action.
            external[0] = SlotStore(root).step(
                "adventure", original["actions"][0],
                expected_head=original["head"],
            )
            return "0"
        return "q"

    returned = play(
        SlotStore(root), "adventure", read=choose,
        write=messages.append, ascii_mode=True,
    )
    authoritative = SlotStore(root).load("adventure")
    assert prompted[0] == 2
    assert external[0] is not None
    assert returned["head"] == external[0]["head"] == authoritative["head"]
    assert returned["revision"] == authoritative["revision"] == 1
    assert SlotStore(root).audit("adventure")["audit_entries"] == 1
    assert any("refreshing authoritative slot" in line for line in messages)


def test_stale_terminal_export_refreshes_authoritative_save(tmp_path):
    root = tmp_path / "saves"
    initial = SlotStore(root).new("adventure")
    messages = []
    prompted = [0]
    updated = [None]

    def choose(_prompt: str) -> str:
        prompted[0] += 1
        if prompted[0] == 1:
            updated[0] = SlotStore(root).step(
                "adventure", initial["actions"][0],
                expected_head=initial["head"],
            )
            return "e"
        return "q"

    returned = play(
        SlotStore(root), "adventure", read=choose,
        write=messages.append, ascii_mode=True,
    )
    from skeleton.game.gameplay.ridge_rescue.campaign import verify_export

    paths = [line.removeprefix("Exported: ") for line in messages
             if line.startswith("Exported: ")]
    assert len(paths) == 1
    from pathlib import Path
    exported = verify_export(Path(paths[0]).read_bytes())
    assert updated[0] is not None
    assert returned["head"] == exported["head"] == updated[0]["head"]
    assert returned["revision"] == updated[0]["revision"] == 1
    assert SlotStore(root).audit("adventure")["audit_entries"] == 1
