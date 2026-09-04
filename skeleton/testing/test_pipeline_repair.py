"""Pipeline repair tests."""
from __future__ import annotations

from skeleton.intelligence.pipeline_repair import attempt_dialogue_repair, attempt_npc_repair
from skeleton.organism.quality_state import latest_repair


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
