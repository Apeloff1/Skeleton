"""An unknown gate does not open, and the word accepted is not a yes."""

import pytest

from skeleton.intelligence.narrative import DialogueChoice, DialogueGraph, DialogueNode, DialogueState
from skeleton.intelligence.repair_autonomy import run_multi_pass


def test_an_unknown_requirement_blocks_the_choice() -> None:
    graph = DialogueGraph({
        "start": DialogueNode("start", "Hello", (
            DialogueChoice("open", "Open", "bond", {"trust:marina": 20}),
            DialogueChoice("gold", "Pay", "bond", requirements={"gold": 10}),
        )),
        "bond": DialogueNode("bond", "Trusted"),
    })
    state = DialogueState("start")
    assert [choice.id for choice in graph.available_choices(state)] == ["open"]
    with pytest.raises(ValueError):
        graph.advance(state, "gold")


def test_a_string_yes_does_not_accept_the_repair(tmp_path) -> None:
    session = run_multi_pass(
        "forge",
        "spec",
        lambda **kw: {"ok": "false", "before": {"score": 0.2}, "after": {"score": 0.9}},
        root=tmp_path,
        max_passes=1,
    )
    assert session.final_accepted is False
    assert session.status == "exhausted"
    accepted = run_multi_pass(
        "forge",
        "spec",
        lambda **kw: {"ok": True, "before": {"score": 0.2}, "after": {"score": 0.9}},
        root=tmp_path,
        max_passes=1,
    )
    assert accepted.final_accepted is True
