"""Atomic structural edits integrate original prompt plans and real quest replay."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest, quest_progress,
)
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    PLAN_SCHEMA, compile_prompt_quest_plan, publish_prompt_quest_plan,
    restore_prompt_quest_plan,
)
from skeleton.ai.game_builder.studio_quest_structural_edit import (
    compile_quest_structural_edit, replay_quest_structural_edit,
)


def original():
    return {
        "schema": PLAN_SCHEMA, "project_id": "tidal-lantern",
        "prompt": "Original lighthouse expedition with a rescued archivist.",
        "originality_attested": True,
        "stages": [
            {"id": "beacon", "prerequisites": [], "alternatives": ["light"],
             "reward": "lit", "choice_effects": {}},
            {"id": "harbor", "prerequisites": ["beacon"], "alternatives": ["sail"],
             "reward": "arrived", "choice_effects": {}},
        ],
        "endings": [{"id": "safe", "requires": ["lit", "arrived"]}],
    }


def baseline():
    plan = original()
    return compile_prompt_quest_plan(
        plan, authorized=True, expected_plan_digest=_digest(plan))


def changes():
    return [
        {"op": "add_stage", "id": "archive", "value": {
            "id": "archive", "prerequisites": ["harbor"],
            "alternatives": ["rescue", "leave"], "reward": "archive_open",
            "choice_effects": {"rescue": ["choice:archive:safe"]}}},
        {"op": "add_ending", "id": "archive_saved", "value": {
            "id": "archive_saved", "requires": ["choice:archive:safe"]}},
    ]


def compile_edits(source=None, edits=None, **kw):
    source = source if source is not None else baseline()
    edits = edits if edits is not None else changes()
    options = {
        "authorized": True, "expected_baseline_digest": source["receipt_digest"]}
    options.update(kw)
    return compile_quest_structural_edit(source, edits, **options)


def test_atomic_edit_compiles_and_new_ending_is_playable():
    source = baseline()
    result = compile_edits(source)
    candidate = result["candidate_compilation"]
    session = replay_quest(
        candidate["documents"],
        [["beacon", "light"], ["harbor", "sail"], ["archive", "rescue"]],
        authorized=True)
    assert "archive_saved" in quest_progress(
        session, candidate["documents"])["sandbox_endings_eligible"]
    assert len(source["plan"]["stages"]) == 2
    assert len(candidate["plan"]["stages"]) == 3
    assert result["source_changed"]
    assert not result["native_gameplay_verified"]
    assert replay_quest_structural_edit(
        result, authorized=True,
        expected_baseline_digest=source["receipt_digest"]) == result


def test_replace_reorder_and_remove_are_full_graph_validated():
    source = baseline()
    # Independent source reordering must retain graph constraints.
    with pytest.raises(StudioQuestError):
        compile_edits(source, [
            {"op": "reorder_stages", "id": "stages",
             "value": ["harbor", "beacon"]}])
    revised = compile_edits(source, [
        {"op": "remove_ending", "id": "safe", "value": None},
        {"op": "add_ending", "id": "farewell",
         "value": {"id": "farewell", "requires": ["arrived"]}},
        {"op": "replace_stage", "id": "harbor", "value": {
            "id": "harbor", "prerequisites": ["beacon"],
            "alternatives": ["sail", "wait"], "reward": "arrived",
            "choice_effects": {}}},
    ])
    assert [e["id"] for e in revised["candidate_compilation"]["plan"]["endings"]] == ["farewell"]
    assert revised["candidate_compilation"]["plan"]["stages"][1]["alternatives"] == ["sail", "wait"]


def test_stale_lease_duplicate_id_and_invalid_graph_fail_closed():
    source = baseline()
    with pytest.raises(PermissionError):
        compile_edits(source, authorized=False)
    with pytest.raises(StudioQuestError, match="stale"):
        compile_edits(source, expected_baseline_digest="0" * 64)
    with pytest.raises(StudioQuestError, match="duplicate"):
        compile_edits(source, [{"op": "add_stage", "id": "beacon", "value": {
            "id": "beacon"}}])
    with pytest.raises(StudioQuestError):
        compile_edits(source, [{"op": "remove_stage", "id": "beacon", "value": None}])
    with pytest.raises(StudioQuestError):
        compile_edits(source, [{"op": "replace_prompt", "id": "prompt",
                                "value": "x" * 5000}])
    with pytest.raises(StudioQuestError):
        compile_edits(source, [{"op": "replace_prompt", "id": "prompt",
                                "value": "Valid"}, {"op": "bogus",
                                "id": "prompt", "value": "bad"}])
    forged = deepcopy(compile_edits(source))
    forged["candidate_compilation"]["native_gameplay_verified"] = True
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_quest_structural_edit(
            forged, authorized=True,
            expected_baseline_digest=source["receipt_digest"])


def test_private_cli_and_explicit_jeeves_authoring(tmp_path, capsys):
    from scripts.studio_quest_structural_edit_cli import main
    from skeleton.ai.agents.jeeves.studio_quest_structural_edit_tool import (
        REQUEST_SCHEMA, execute_quest_structural_edit_tool,
    )
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    source = baseline()
    old, new = tmp_path / "baseline", tmp_path / "candidate"
    old.mkdir(mode=0o700)
    new.mkdir(mode=0o700)
    publish_prompt_quest_plan(source, old, authorized=True)
    assert main([
        "--baseline-dir", str(old), "--expected-baseline", source["receipt_digest"],
        "--edits-json", json.dumps(changes()), "--publish-candidate", str(new),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["file_write_performed"]
    assert restore_prompt_quest_plan(new, authorized=True) == payload["proof"]["candidate_compilation"]
    request = {
        "schema": REQUEST_SCHEMA, "baseline_compilation": source,
        "expected_baseline_digest": source["receipt_digest"], "edits": changes(),
    }
    direct = execute_quest_structural_edit_tool(request, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(
            {"tool": "studio_quest_structural_edit", "arguments": request},
            authorized=True)
    routed = route_world_tool(
        {"tool": "studio_quest_structural_edit", "arguments": request},
        authorized=True, allow_authoring=True)
    assert routed["result"] == direct
    assert routed["file_write_performed"] is False
