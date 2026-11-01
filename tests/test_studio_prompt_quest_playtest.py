"""End-to-end original prompt plan -> canonical playable ending handoff."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _digest
from skeleton.ai.game_builder.studio_prompt_quest_plan import (
    PLAN_SCHEMA, compile_prompt_quest_plan, publish_prompt_quest_plan,
)
from skeleton.ai.game_builder.studio_prompt_quest_playtest import (
    compile_prompt_quest_playtest, replay_prompt_quest_playtest,
)


def original():
    return {
        "schema": PLAN_SCHEMA, "project_id": "new-tide",
        "prompt": "Original island mystery about a lantern and a locked pier.",
        "originality_attested": True,
        "stages": [
            {"id": "light", "prerequisites": [],
             "alternatives": ["ignite", "wait"], "reward": "lamp",
             "choice_effects": {"ignite": ["choice:light:lit"]}},
            {"id": "sail", "prerequisites": ["light"],
             "alternatives": ["go"], "reward": "sailed",
             "choice_effects": {}},
        ],
        "endings": [
            {"id": "safe", "requires": ["choice:light:lit", "sailed"]},
            {"id": "unknown", "requires": ["unverified_world_token"]},
        ],
    }


def compilation():
    source = original()
    return compile_prompt_quest_plan(
        source, authorized=True, expected_plan_digest=_digest(source))


def run(source=None, **changes):
    source = source if source is not None else compilation()
    options = {
        "target_ending": "safe", "max_states": 128, "max_depth": 4,
        "authorized": True,
        "expected_compilation_digest": source["receipt_digest"],
    }
    options.update(changes)
    return compile_prompt_quest_playtest(source, **options)


def test_replay_verified_prompt_to_ending_handoff():
    source = compilation()
    result = run(source)
    assert result["status"] == "found"
    assert result["sandbox_playable_handoff_verified"]
    assert result["playable_handoff"]["authored_actions"] == [
        ["light", "ignite"], ["sail", "go"]]
    assert not result["native_gameplay_verified"]
    assert not result["release_certified"]
    assert replay_prompt_quest_playtest(
        result, authorized=True,
        expected_compilation_digest=source["receipt_digest"]) == result


def test_budget_and_unobserved_evidence_fail_closed():
    source = compilation()
    limited = run(source, max_states=1)
    assert limited["status"] == "inconclusive"
    assert limited["playable_handoff"] is None
    unknown = run(source, target_ending="unknown")
    assert unknown["status"] == "unreachable"
    assert not unknown["sandbox_playable_handoff_verified"]
    with pytest.raises(StudioQuestError, match="stale"):
        run(source, expected_compilation_digest="0" * 64)
    with pytest.raises(PermissionError):
        run(source, authorized=False)
    forged = deepcopy(run(source))
    forged["playable_handoff"]["quest_session_digest"] = "0" * 64
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_prompt_quest_playtest(
            forged, authorized=True,
            expected_compilation_digest=source["receipt_digest"])


def test_cli_and_jeeves_parity_with_private_compilation(monkeypatch, tmp_path, capsys):
    import skeleton.ai.agents.jeeves.studio_prompt_quest_playtest_tool as adapter
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    from scripts.studio_prompt_quest_playtest_cli import main
    source = compilation()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    publish_prompt_quest_plan(source, private, authorized=True)
    assert main([
        "--plan-directory", str(private),
        "--expected-compilation", source["receipt_digest"],
        "--target-ending", "safe",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["playtest"]["status"] == "found"
    request = {
        "schema": adapter.REQUEST_SCHEMA, "compilation": source,
        "expected_compilation_digest": source["receipt_digest"],
        "target_ending": "safe", "max_states": 128, "max_depth": 4,
    }
    direct = adapter.execute_prompt_quest_playtest_tool(request, authorized=True)
    routed = route_world_tool(
        {"tool": "studio_original_prompt_quest_playtest",
         "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert not routed["file_write_performed"]
