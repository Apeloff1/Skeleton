"""Pipeline repair tests."""
from __future__ import annotations

from skeleton.intelligence.pipeline_repair import attempt_dialogue_repair, attempt_npc_repair
from skeleton.organism.quality_state import latest_repair
from skeleton.pipelines.dialogue import DialogueTree, quality_check
from skeleton.pipelines.npc import NpcPipeline


def test_attempt_npc_repair_fills_missing_fields(tmp_path):
    out = attempt_npc_repair({"name": "", "archetype": "", "persona": {}, "dialogue_tree": [], "behaviour_graph": []}, description="guardian mentor", root=tmp_path)
    assert out["changed"] == 1
    assert out["spec"]["name"]
    assert latest_repair(root=tmp_path, surface="npc")["kind"] == "repair"


def test_attempt_dialogue_repair_seeds_minimal_tree(tmp_path):
    out = attempt_dialogue_repair({"entry": "", "nodes": {}}, description="simple dialogue", root=tmp_path)
    assert out["changed"] == 1
    assert out["tree"]["entry"] == "root"
    assert latest_repair(root=tmp_path, surface="dialogue")["kind"] == "repair"


def test_npc_pipeline_can_repair_once(tmp_path):
    pipe = NpcPipeline(root=tmp_path, generator=lambda d, p: {"speech_register": "formal"})
    spec = pipe.run("broken npc", repair=True)
    payload = spec.to_dict()
    assert "repair" in payload


def test_dialogue_quality_check_can_repair_once(tmp_path):
    tree = DialogueTree(tree_id="dlg", entry="", nodes={})
    checked = quality_check(tree, description="broken dialogue", root=tmp_path, repair=True)
    payload = checked.to_dict()
    assert "repair" in payload
