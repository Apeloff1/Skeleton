"""Pipeline repair tests."""
from __future__ import annotations

import pytest
from skeleton.kernel.errors import GenerationError

from skeleton.intelligence.pipeline_repair import attempt_dialogue_repair, attempt_npc_repair
from skeleton.organism.quality_state import latest_repair
from skeleton.pipelines.dialogue import DialogueTree, quality_check
from skeleton.pipelines.npc import NpcPipeline


def test_attempt_npc_repair_reports_missing_fields_without_inventing_content(tmp_path):
    out = attempt_npc_repair({"name": "", "archetype": "", "persona": {}, "dialogue_tree": [], "behaviour_graph": []}, description="guardian mentor", root=tmp_path)
    assert out["changed"] == 0
    assert out["ok"] == 0
    assert out["spec"]["name"] == ""
    assert out["before"] == out["after"]
    assert out["actions"] and all(action["applied"] == 0 for action in out["actions"])
    assert latest_repair(root=tmp_path, surface="npc")["kind"] == "repair"


def test_attempt_dialogue_repair_reports_missing_tree_without_fabrication(tmp_path):
    out = attempt_dialogue_repair({"entry": "", "nodes": {}}, description="simple dialogue", root=tmp_path)
    assert out["changed"] == 0
    assert out["ok"] == 0
    assert out["tree"] == {"entry": "", "nodes": {}}
    assert out["before"] == out["after"]
    assert latest_repair(root=tmp_path, surface="dialogue")["kind"] == "repair"


def test_npc_pipeline_rejects_incomplete_generation_even_with_repair_enabled(tmp_path):
    pipe = NpcPipeline(root=tmp_path, generator=lambda d, p: {"speech_register": "formal"})
    with pytest.raises(GenerationError, match="incomplete persona"):
        pipe.run("broken npc", repair=True)


def test_dialogue_quality_check_can_repair_once(tmp_path):
    tree = DialogueTree(tree_id="dlg", entry="", nodes={})
    checked = quality_check(tree, description="broken dialogue", root=tmp_path, repair=True)
    payload = checked.to_dict()
    assert "repair" in payload
