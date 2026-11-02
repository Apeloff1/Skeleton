"""Browser quest choice effects must match canonical ending eligibility."""
from __future__ import annotations

import copy
import json
import os
import stat

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, quest_progress,
    replay_quest, start_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_story_html import (
    render_story_html, story_source,
)
from skeleton.ai.game_builder.studio_story_browser_parity import (
    PROMPT, SCHEMA, FILENAME, compile_story_browser_parity,
    propose_story_browser_parity, replay_story_browser_parity,
    compile_story_browser_handoff, publish_story_browser_parity,
    restore_story_browser_parity,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    stage = docs["quest"].get("stage_graph") or docs["quest"]["stages"]
    first = stage[0]
    choice = first["alternatives"][0]
    token = "choice:" + first["id"] + ":browser_parity"
    first["choice_effects"] = {choice: [token]}
    docs["narrative"]["endings"].append({
        "id": "browser_parity_ending", "requires": [token]})
    source = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    return docs, [[first["id"], choice]], {
        "authorized": True, "expected_source_digest": source.source_digest,
        "expected_initial_session_digest": initial.digest,
    }


def test_choice_effects_unlock_authored_browser_endings():
    docs, actions, leases = fixture()
    receipt = compile_story_browser_parity(docs, actions, **leases)
    assert receipt["schema"] == SCHEMA
    assert receipt["browser_projection_parity_verified"] is True
    assert receipt["javascript_runtime_executed"] is False
    assert "browser_parity_ending" in receipt["canonical_eligible_endings"]
    assert receipt["applied_choice_effects"][0]["earned_choice_effects"] == [
        "choice:" + actions[0][0] + ":browser_parity"]
    assert "browser_parity_ending" in quest_progress(
        replay_quest(docs, actions, authorized=True), docs)["sandbox_endings_eligible"]
    source = story_source(docs)
    assert source["stages"][0]["choice_effects"][actions[0][1]]
    html = render_story_html(docs)
    assert b"stage.choice_effects[option]" in html
    assert b"browser_parity_ending" in html
    assert replay_story_browser_parity(docs, receipt, authorized=True) == receipt
    manifest, handoff = compile_story_browser_handoff(
        docs, receipt, authorized=True)
    assert handoff == html
    assert manifest["canonical_quest_replay_verified"] is True
    assert manifest["native_genre_runtime_verified"] is False


def test_first_choice_prompt_is_deterministic_and_source_bound():
    docs, _, leases = fixture()
    first = propose_story_browser_parity(docs, PROMPT, **leases)
    second = propose_story_browser_parity(docs, PROMPT, **leases)
    assert first == second
    assert first["model_inference_performed"] is False
    assert first["detail"]["canonical_eligible_endings"] == [
        row["ending_id"] for row in first["detail"]["browser_endings"]
        if row["eligible"]]
    with pytest.raises(StudioQuestError):
        propose_story_browser_parity(docs, "invent external evidence", **leases)


@pytest.mark.parametrize("bad", [
    [["forged", "action"]], [[True, "choice"]], [["stage", False]],
    [["stage", "choice", "extra"]], "not-actions",
    [["stage", "choice"]] * 65,
])
def test_invalid_browser_history_fails_closed(bad):
    docs, _, leases = fixture()
    with pytest.raises(StudioQuestError):
        compile_story_browser_parity(docs, bad, **leases)


def test_stale_lease_authority_and_forged_receipt_rejected():
    docs, actions, leases = fixture()
    receipt = compile_story_browser_parity(docs, actions, **leases)
    with pytest.raises(PermissionError):
        compile_story_browser_parity(
            docs, actions, **dict(leases, authorized=1))
    with pytest.raises(StudioQuestError):
        compile_story_browser_parity(
            docs, actions, **dict(leases, expected_source_digest="0" * 64))
    for key, value in [
        ("browser_projection_parity_verified", 1),
        ("javascript_runtime_executed", True),
        ("release_certified", True),
        ("receipt_digest", "0" * 64),
        ("browser_endings", [{**receipt["browser_endings"][0],
                              "eligible": 1}] + receipt["browser_endings"][1:]),
    ]:
        changed = copy.deepcopy(receipt)
        changed[key] = value
        with pytest.raises(StudioQuestError):
            replay_story_browser_parity(docs, changed, authorized=True)
    docs["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        replay_story_browser_parity(docs, receipt, authorized=True)


def test_private_publish_restore_no_overwrite_and_no_symlinks(tmp_path):
    docs, actions, leases = fixture()
    receipt = compile_story_browser_parity(docs, actions, **leases)
    assert publish_story_browser_parity(
        docs, receipt, tmp_path, authorized=True)["file_write_performed"] is True
    path = tmp_path / FILENAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert restore_story_browser_parity(
        docs, tmp_path, **leases) == receipt
    with pytest.raises(FileExistsError):
        publish_story_browser_parity(docs, receipt, tmp_path, authorized=True)
    path.unlink()
    path.symlink_to(tmp_path / "absent")
    with pytest.raises(OSError):
        restore_story_browser_parity(docs, tmp_path, **leases)
    path.unlink()
    path.write_text(json.dumps(receipt))
    os.chmod(path, 0o600)
    with pytest.raises(StudioQuestError):
        restore_story_browser_parity(docs, tmp_path, **leases)
    path.write_text('{"schema":"a","schema":"b"}')
    with pytest.raises(StudioQuestError):
        restore_story_browser_parity(docs, tmp_path, **leases)


def test_failed_directory_durability_rolls_back(tmp_path, monkeypatch):
    from skeleton.ai.game_builder import studio_story_browser_parity as owner
    docs, actions, leases = fixture()
    receipt = compile_story_browser_parity(docs, actions, **leases)
    original = owner.os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(owner.os.fstat(fd).st_mode):
            raise OSError("simulated directory durability failure")
        return original(fd)
    monkeypatch.setattr(owner.os, "fsync", fail_directory)
    with pytest.raises(OSError):
        publish_story_browser_parity(docs, receipt, tmp_path, authorized=True)
    assert not list(tmp_path.iterdir())


def test_typed_jeeves_router_and_cli(tmp_path, monkeypatch, capsys):
    from skeleton.ai.agents.jeeves import studio_story_browser_parity_tool as tool
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool, world_tool_catalog,
    )
    from scripts import studio_story_browser_parity_cli as cli
    docs, actions, leases = fixture()
    monkeypatch.setattr(tool, "read_blueprint", lambda _: docs)
    monkeypatch.setattr(cli, "read_blueprint", lambda _: docs)
    request = {
        "schema": tool.REQUEST_SCHEMA, "project_id": PROJECT,
        "actions": actions,
        "expected_source_digest": leases["expected_source_digest"],
        "expected_initial_session_digest": leases["expected_initial_session_digest"],
    }
    name = tool.story_browser_parity_tool_schema()["name"]
    assert name in {x["name"] for x in world_tool_catalog()["tools"]}
    assert route_world_tool(
        {"tool": name, "arguments": request}, authorized=True
    )["result"]["detail"]["browser_projection_parity_verified"] is True
    with pytest.raises(PermissionError):
        tool.execute_story_browser_parity_tool(request, authorized=False)
    flags = [
        "--project", PROJECT,
        "--expected-source", leases["expected_source_digest"],
        "--expected-session", leases["expected_initial_session_digest"],
    ]
    authoring = tmp_path / "authoring.json"
    authoring.write_text(json.dumps({"actions": actions}))
    os.chmod(authoring, 0o600)
    assert cli.main(flags + ["--authoring-file", str(authoring),
                             "--publish", str(tmp_path), "--playable"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["playable_handoff"]["canonical_quest_replay_verified"] is True
    assert cli.main(flags + ["--restore", str(tmp_path)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["detail"] == first["detail"]
