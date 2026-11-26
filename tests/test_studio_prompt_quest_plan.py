"""Typed original quest prompt -> compile -> edit -> persist -> replay."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest, quest_progress,
)
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    PLAN_SCHEMA, FILENAME, compile_prompt_quest_plan,
    replay_prompt_quest_plan, revise_prompt_quest_plan,
    publish_prompt_quest_plan, restore_prompt_quest_plan,
    render_prompt_quest_html,
)


def plan():
    return {
        "schema": PLAN_SCHEMA, "project_id": "quiet-harbor",
        "prompt": "An original lighthouse mystery about a missing tide chart.",
        "originality_attested": True,
        "stages": [
            {"id": "search", "prerequisites": [], "alternatives": ["read", "leave"],
             "reward": "chart_found", "choice_effects": {
                 "read": ["choice:search:read"]}},
            {"id": "return", "prerequisites": ["search"],
             "alternatives": ["deliver"], "reward": "returned",
             "choice_effects": {}},
        ],
        "endings": [
            {"id": "truth", "requires": ["chart_found", "returned"]},
            {"id": "secret", "requires": ["choice:search:read"]},
        ],
    }


def compile_plan(value=None):
    value = value if value is not None else plan()
    return compile_prompt_quest_plan(
        value, authorized=True, expected_plan_digest=_digest(value))


def test_prompt_typed_plan_compiles_to_actual_quest_and_playable_handoff():
    receipt = compile_plan()
    assert receipt["plan_digest"] == _digest(plan())
    assert receipt["sandbox_quest_handoff_verified"]
    assert not receipt["native_gameplay_verified"]
    assert not receipt["release_certified"]
    session = replay_quest(
        receipt["documents"], [["search", "read"], ["return", "deliver"]],
        authorized=True)
    assert quest_progress(
        session, receipt["documents"])["sandbox_endings_eligible"] == [
            "truth", "secret"]
    assert replay_prompt_quest_plan(receipt, authorized=True) == receipt


def test_authoring_cas_revision_recompiles_and_invalidates_old_source():
    receipt = compile_plan()
    revised = revise_prompt_quest_plan(
        receipt, {"kind": "stage_reward", "id": "search",
                  "value": "recovered_chart"},
        authorized=True, expected_receipt_digest=receipt["receipt_digest"])
    assert revised["quest_source_digest"] != receipt["quest_source_digest"]
    assert revised["documents"]["quest"]["stage_graph"][0]["reward"] == "recovered_chart"
    assert receipt["documents"]["quest"]["stage_graph"][0]["reward"] == "chart_found"
    with pytest.raises(StudioQuestError, match="stale"):
        revise_prompt_quest_plan(
            receipt, {"kind": "prompt", "id": "prompt", "value": "Changed"},
            authorized=True, expected_receipt_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        revise_prompt_quest_plan(
            receipt, {"kind": "ending_requirements", "id": "truth",
                      "value": ["choice:search:forged"]},
            authorized=True, expected_receipt_digest=receipt["receipt_digest"])


def test_invalid_typed_plans_fail_closed_and_never_infer_rights():
    value = plan()
    value["originality_attested"] = False
    with pytest.raises(StudioQuestError, match="attestation"):
        compile_plan(value)
    value = plan()
    value["stages"][1]["prerequisites"] = ["missing"]
    with pytest.raises(StudioQuestError):
        compile_plan(value)
    value = plan()
    value["prompt"] = "<script>alert(1)</script>"
    html = render_prompt_quest_html(compile_plan(value), authorized=True)
    assert b"<script>" not in html
    assert b"&lt;script&gt;" in html
    assert b"default-src 'none'" in html
    forged = deepcopy(compile_plan())
    forged["native_gameplay_verified"] = 0
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_prompt_quest_plan(forged, authorized=True)
    forged = deepcopy(compile_plan())
    forged["native_gameplay_verified"] = True
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_prompt_quest_plan(forged, authorized=True)


def test_private_publication_duplicate_key_and_symlink(tmp_path):
    receipt = compile_plan()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    assert publish_prompt_quest_plan(
        receipt, private, authorized=True)["file_write_performed"]
    assert restore_prompt_quest_plan(private, authorized=True) == receipt
    with pytest.raises(FileExistsError):
        publish_prompt_quest_plan(receipt, private, authorized=True)
    target = private / FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_prompt_quest_plan(private, authorized=True)
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_prompt_quest_plan(private, authorized=True)


def test_jeeves_authoring_gate_and_cli_round_trip(monkeypatch, capsys):
    import skeleton.ai.agents.jeeves.studio_prompt_quest_plan_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    import scripts.studio_prompt_quest_plan_cli as cli
    authored = plan()
    request = {
        "schema": adapter.REQUEST_SCHEMA, "plan": authored,
        "expected_plan_digest": _digest(authored),
    }
    direct = adapter.execute_prompt_quest_plan_tool(request, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(
            {"tool": "studio_original_prompt_quest_plan",
             "arguments": request}, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_prompt_quest_plan",
         "arguments": request}, authorized=True, allow_authoring=True)
    assert routed["result"] == direct
    assert not routed["file_write_performed"]
    assert cli.main(["--plan-json", json.dumps(authored)]) == 0
    assert json.loads(capsys.readouterr().out)["compilation"] == direct["detail"]
