"""Exercise a real menu-driven two-chapter win across a cold process boundary.

This is source-level acceptance, not a Windows device certification.
Every action is selected from the menu exposed by the canonical engine.
"""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore
from skeleton.game.gameplay.ridge_rescue.campaign import verify_export


def test_menu_play_earns_both_endings_then_restarts_and_exports(tmp_path):
    root = tmp_path / "consumer-saves"
    store = SlotStore(root)
    planned = list(acceptance_actions("protect"))
    messages = []
    consumed = []

    def choose(_prompt):
        current = SlotStore(root).load("journey")
        if current["status"] == "completed":
            return "q"
        assert planned, "game requested another turn after the canonical ending"
        wanted = planned.pop(0)
        assert wanted in current["actions"], (
            "the canonical winning route is not reachable from the visible menu",
            wanted, current["actions"],
        )
        consumed.append(wanted)
        return str(current["actions"].index(wanted))

    finished = play(store, "journey", read=choose, write=messages.append)
    assert not planned, "the menu reached a terminal state before the full route"
    assert finished["status"] == "completed"
    assert finished["revision"] == len(consumed)
    assert len(finished["session"]["completed"]) == 2
    assert all(
        chapter["state"]["status"].startswith("won:")
        for chapter in finished["session"]["completed"]
    )
    assert any("Victory:" in line for line in messages)
    assert store.audit("journey")["verified"] is True

    # A separate SlotStore instance models a cold restart with no shared state.
    reopened = SlotStore(root)
    resumed = play(reopened, "journey", read=lambda _: "q", write=lambda _: None)
    assert resumed["head"] == finished["head"]
    assert resumed["revision"] == finished["revision"]
    exported = reopened.export("journey")
    verified = verify_export(exported.read_bytes())
    assert verified["head"] == finished["head"]
    assert verified["status"] == "completed"
    assert reopened.audit("journey")["audit_entries"] == len(consumed)


def test_menu_eof_preserves_last_committed_turn_after_restart(tmp_path):
    root = tmp_path / "consumer-saves"
    initial = SlotStore(root).new("journey")
    output = []
    answers = iter(["0"])
    after_eof = play(
        SlotStore(root), "journey", read=lambda _: next(answers),
        write=output.append,
    )
    assert after_eof["revision"] == 1
    assert after_eof["head"] != initial["head"]
    resumed = SlotStore(root).load("journey")
    assert resumed["head"] == after_eof["head"]
    assert resumed["revision"] == 1
    assert SlotStore(root).audit("journey")["verified"] is True
