"""Original story bookmark source custody, UI/CLI and Jeeves regressions."""
from __future__ import annotations

from hashlib import sha256
import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source, render_story_html
from skeleton.ai.game_builder.studio_story_reading_bookmark import (
    REQUEST_SCHEMA as BOOKMARK_REQUEST_SCHEMA,
    compile_story_reading_bookmark, replay_story_reading_bookmark,
    render_story_reading_bookmark_html,
)
from skeleton.ai.agents.jeeves.studio_story_reading_bookmark_tool import (
    REQUEST_SCHEMA, execute_story_reading_bookmark_tool,
    story_reading_bookmark_tool_schema,
)
from skeleton.ai.game_builder.studio_story_reading_bookmark_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def source():
    docs = read_blueprint(PROJECT)
    return docs, story_source(docs)


def request(story, note="Return after reviewing the next scene"):
    return {
        "schema": BOOKMARK_REQUEST_SCHEMA,
        "stage_id": story["stages"][0]["id"], "reader_note": note,
    }


def compile_bookmark(docs, story, req=None):
    return compile_story_reading_bookmark(
        docs, request(story) if req is None else req,
        authorized=True, expected_source_digest=story["source_digest"])


def test_reader_bookmark_replays_canonical_stage_without_committing_quest():
    docs, story = source()
    first = compile_bookmark(docs, story)
    assert first == compile_bookmark(docs, story)
    assert first["stage_count"] == len(story["stages"])
    assert first["sandbox_playable_html_compiled"] is True
    assert first["sandbox_playable_html_sha256"] == sha256(render_story_html(docs)).hexdigest()
    assert first["stage_index"] == 0
    assert first["previous_stage_id"] is None
    assert first["stage"]["authored_goal"] == story["stages"][0]["authored_goal"]
    assert first["stage"]["alternatives"] == story["stages"][0]["alternatives"]
    assert first["reading_position_only"] is True
    assert first["quest_action_committed"] is False
    assert first["release_certified"] is False
    assert replay_story_reading_bookmark(
        docs, first, authorized=True,
        expected_source_digest=story["source_digest"]) == first


def test_bookmark_next_and_previous_stage_links_are_authored_only():
    docs, story = source()
    assert len(story["stages"]) >= 3
    middle = compile_bookmark(docs, story, {
        "schema": BOOKMARK_REQUEST_SCHEMA,
        "stage_id": story["stages"][1]["id"], "reader_note": "Middle scene",
    })
    assert middle["previous_stage_id"] == story["stages"][0]["id"]
    assert middle["next_stage_id"] == story["stages"][2]["id"]
    assert middle["stage_index"] == 1
    assert middle["quest_action_committed"] is False


def test_forged_stage_context_and_stale_source_fail_closed():
    docs, story = source()
    original = compile_bookmark(docs, story)
    forged = copy.deepcopy(original)
    forged["stage"]["authored_goal"] = "Forged canonical goal"
    with pytest.raises(StudioQuestError, match="replay"):
        replay_story_reading_bookmark(
            docs, forged, authorized=True,
            expected_source_digest=story["source_digest"])
    forged = copy.deepcopy(original)
    forged["release_certified"] = True
    with pytest.raises(StudioQuestError):
        replay_story_reading_bookmark(
            docs, forged, authorized=True,
            expected_source_digest=story["source_digest"])
    with pytest.raises(StudioQuestError, match="stale"):
        compile_story_reading_bookmark(
            docs, request(story), authorized=True,
            expected_source_digest="0" * 64)
    with pytest.raises(PermissionError):
        compile_story_reading_bookmark(
            docs, request(story), authorized=False,
            expected_source_digest=story["source_digest"])


@pytest.mark.parametrize("bad", [
    {}, {"stage_id": "first", "reader_note": "note"},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "missing", "reader_note": "note"},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "../escape", "reader_note": "note"},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "first", "reader_note": ""},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "first", "reader_note": "a\nb"},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "first", "reader_note": True},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "first", "reader_note": " "},
    {"schema": BOOKMARK_REQUEST_SCHEMA, "stage_id": "first",
     "reader_note": "a" * 241},
])
def test_invalid_bookmark_requests_fail_closed(bad):
    docs, story = source()
    with pytest.raises(StudioQuestError):
        compile_bookmark(docs, story, bad)


def test_static_html_escapes_untrusted_note_and_keeps_strict_csp():
    docs, story = source()
    note = "<img src=x onerror=alert(1)>"
    receipt = compile_bookmark(docs, story, request(story, note))
    html = render_story_reading_bookmark_html(
        docs, receipt, authorized=True,
        expected_source_digest=story["source_digest"]).decode()
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html
    assert "default-src &#x27;none&#x27;" in html
    assert "<script" not in html
    assert receipt["bookmark_digest"] in html


def test_jeeves_reader_bookmark_is_source_leased_and_authoring_gated():
    _, story = source()
    req = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_quest_source_digest": story["source_digest"],
        "stage_id": story["stages"][0]["id"],
        "reader_note": "Read this again", "format": "json",
    }
    assert story_reading_bookmark_tool_schema()["parameters"][
        "additionalProperties"] is False
    with pytest.raises(PermissionError):
        execute_story_reading_bookmark_tool(req)
    result = execute_story_reading_bookmark_tool(req, authorized=True)
    assert json.loads(result["content"])["stage"]["stage_id"] == req["stage_id"]
    assert result["file_write_performed"] is False
    assert result["quest_action_committed"] is False
    with pytest.raises(StudioQuestError):
        execute_story_reading_bookmark_tool({
            **req, "expected_quest_source_digest": "0" * 64}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_story_reading_bookmark_tool({
            **req, "allow_authoring": True}, authorized=True)


def test_router_rejects_bookmark_without_explicit_authoring_permission():
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool, world_tool_catalog,
    )
    _, story = source()
    tools = {item["name"]: item for item in world_tool_catalog()["tools"]}
    assert tools["studio_original_story_reading_bookmark"][
        "explicit_authoring_permission_required"] is True
    req = {
        "tool": "studio_original_story_reading_bookmark",
        "arguments": {
            "schema": REQUEST_SCHEMA, "project_id": PROJECT,
            "expected_quest_source_digest": story["source_digest"],
            "stage_id": story["stages"][0]["id"],
            "reader_note": "Revisit", "format": "html",
        },
    }
    with pytest.raises(PermissionError):
        route_world_tool(req, authorized=True)
    result = route_world_tool(req, authorized=True, allow_authoring=True)
    assert result["result"]["content"].startswith("<!doctype html>")
    assert result["release_certified"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX private file custody only")
def test_private_cli_save_restore_and_no_overwrite(tmp_path, monkeypatch, capsys):
    _, story = source()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "request.json").write_text(json.dumps({
        "stage_id": story["stages"][0]["id"], "reader_note": "Revisit scene"}))
    (tmp_path / "request.json").chmod(0o600)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", story["source_digest"],
        "--request-file", "request.json", "--format", "json",
        "--output-file", "bookmark.json", "--trusted-local-operator",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["saved_new_private_file"] is True
    assert (tmp_path / "bookmark.json").stat().st_mode & 0o077 == 0
    assert main(args) == 2
    assert "error:" in capsys.readouterr().err
    restored = [
        "--project-id", PROJECT,
        "--quest-source-digest", story["source_digest"],
        "--restore-file", "bookmark.json", "--format", "html",
        "--output-file", "review.html", "--trusted-local-operator",
    ]
    assert main(restored) == 0
    assert (tmp_path / "review.html").read_text().startswith("<!doctype html>")
    assert (tmp_path / "review.html").stat().st_mode & 0o077 == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow file custody only")
def test_cli_rejects_duplicate_json_and_symlinked_input(
    tmp_path, monkeypatch,
):
    _, story = source()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_text('{"stage_id":"x","stage_id":"y","reader_note":"n"}')
    request_file.chmod(0o600)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", story["source_digest"],
        "--request-file", "request.json", "--format", "html",
        "--output-file", "review.html", "--trusted-local-operator",
    ]
    assert main(args) == 2
    assert not (tmp_path / "review.html").exists()
    request_file.unlink()
    request_file.symlink_to(tmp_path / "missing")
    assert main(args) == 2
    assert not (tmp_path / "review.html").exists()
