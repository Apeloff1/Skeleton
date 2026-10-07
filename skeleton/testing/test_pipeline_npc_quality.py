"""NPC quality integration tests."""
from __future__ import annotations

from skeleton.kernel.events import EventBus
from skeleton.pipelines.npc import NpcPipeline


def test_npc_pipeline_attaches_quality_contract(tmp_path):
    pipe = NpcPipeline(bus=EventBus(), root=tmp_path)
    spec = pipe.run("stoic guardian who counts doorways", name="Gatewatch")
    payload = spec.to_dict()
    assert payload["quality"]["accepted"] is True
    assert payload["quality"]["quality"]["metadata"]["pipeline"] == "npc"
    assert payload["quality_stats"]["runs"] == 1


def test_pipeline_verifiers_use_the_project_policy_root(tmp_path):
    from skeleton.organism.policy_state import set_threshold
    from skeleton.forge.pipelines.game_logic import GameLogicPipeline
    from skeleton.forge.pipelines.dialogue import DialogueTree, quality_check
    for surface in ("npc", "game_logic", "dialogue"):
        set_threshold(surface, 0.91, root=tmp_path)
    npc = NpcPipeline(root=tmp_path).run("stoic guardian who counts doorways", name="Gatewatch")
    game = GameLogicPipeline(root=tmp_path).run("arena combat", title="Arena")
    dialogue = quality_check(DialogueTree(tree_id="test", entry="", nodes={}), root=tmp_path)
    for quality in (npc.quality, game.quality, dialogue.quality):
        assert set(quality["thresholds"].values()) == {0.91}


def test_npc_verifier_does_not_count_nontext_node_identity():
    from skeleton.intelligence.npc_verifier import NpcVerifier
    report = NpcVerifier().verify({"name": "A", "archetype": "guardian", "persona": {"traits": ["stoic"]},
        "dialogue_tree": [{"node_id": 1}, {"line": []}], "behaviour_graph": [{"name": False}, {}]},
        description="stoic guardian")
    assert not report.accepted
    assert report.summary["hard_issues"] == 2
