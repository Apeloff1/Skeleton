"""Dialogue quality integration tests."""
from __future__ import annotations

from skeleton.pipelines.dialogue import DialogueEdge, DialogueNode, DialogueTree, quality_check


def test_dialogue_quality_check_attaches_contract():
    tree = DialogueTree(
        tree_id="dlg1",
        entry="root",
        nodes={
            "root": DialogueNode("root", "npc", "Choose.", [DialogueEdge("Go", "end")]),
            "end": DialogueNode("end", "npc", "Done.", [], terminal=True),
        },
    )
    checked = quality_check(tree, description="choose and end")
    payload = checked.to_dict()
    assert payload["quality"]["accepted"] is True
    assert payload["quality"]["quality"]["metadata"]["pipeline"] == "dialogue"
    assert payload["quality_stats"]["runs"] == 1
