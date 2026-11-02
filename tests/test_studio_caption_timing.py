"""Canonical caption timing edit, typed Jeeves and private CLI regression."""
from __future__ import annotations

from hashlib import sha256
import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_story_html import render_story_html
from skeleton.ai.game_builder.studio_ecosystem_story_accessibility import (
    compile_story_accessibility,
)
from skeleton.ai.game_builder.studio_ecosystem_caption_timing import (
    compile_caption_timing_edit, replay_caption_timing_edit,
    render_caption_timing_review_html,
)
from skeleton.ai.agents.jeeves.studio_caption_timing_tool import (
    REQUEST_SCHEMA, caption_timing_tool_schema, execute_caption_timing_tool,
)
from skeleton.ai.game_builder.studio_caption_timing_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def source():
    docs = read_blueprint(PROJECT)
    original = compile_story_accessibility(docs, authorized=True)
    return docs, original


def compile_edit(docs, original, edits=None):
    return compile_caption_timing_edit(
        docs, {"1": 5000} if edits is None else edits,
        authorized=True, expected_source_digest=original["source_digest"])


def test_timing_edits_preserve_all_canonical_words_and_replay():
    docs, original = source()
    first = compile_edit(docs, original)
    second = compile_edit(docs, original)
    assert first == second
    assert first["caption_count"] == original["caption_count"]
    assert first["canonical_webvtt_sha256"] == original["webvtt_sha256"]
    assert first["sandbox_playable_html_compiled"] is True
    assert first["sandbox_playable_html_sha256"] == sha256(render_story_html(docs)).hexdigest()
    assert first["source_digest"] == original["source_digest"]
    assert first["canonical_words_preserved"] is True
    assert first["audio_sync_verified"] is False
    assert first["release_certified"] is False
    assert first["webvtt_sha256"] == sha256(first["webvtt"].encode()).hexdigest()
    assert first["webvtt"].count(" --> ") == original["caption_count"]
    assert first["timeline"][0]["duration_ms"] == 5000
    assert first["timeline"][0]["start_ms"] == 0
    assert first["timeline"][1]["start_ms"] == 5000
    assert [row["canonical_text"] for row in first["timeline"]] == [
        row["canonical_text"] for row in second["timeline"]]
    assert replay_caption_timing_edit(
        docs, first, authorized=True,
        expected_source_digest=original["source_digest"]) == first


def test_timing_edit_does_not_accept_foreign_words_or_forged_receipts():
    docs, original = source()
    receipt = compile_edit(docs, original)
    forged = copy.deepcopy(receipt)
    forged["timeline"][0]["canonical_text"] = "Invented narrator testimony"
    with pytest.raises(StudioQuestError, match="replay"):
        replay_caption_timing_edit(
            docs, forged, authorized=True,
            expected_source_digest=original["source_digest"])
    forged = copy.deepcopy(receipt)
    forged["audio_sync_verified"] = True
    forged["edit_digest"] = sha256(b"forged").hexdigest()
    with pytest.raises(StudioQuestError):
        replay_caption_timing_edit(
            docs, forged, authorized=True,
            expected_source_digest=original["source_digest"])
    with pytest.raises(StudioQuestError, match="stale"):
        compile_caption_timing_edit(
            docs, {"1": 5000}, authorized=True,
            expected_source_digest="0" * 64)
    with pytest.raises(PermissionError):
        compile_caption_timing_edit(
            docs, {"1": 5000}, authorized=False,
            expected_source_digest=original["source_digest"])


@pytest.mark.parametrize("invalid", [
    {}, {"0": 5000}, {"01": 5000}, {"-1": 5000},
    {"1": True}, {"1": 100}, {"1": 30001}, {"1": "5000"},
    {"1": 5000.0}, {"999": 5000}, {"1": 5000, "01": 6000},
    {"1": 5000, "untrusted": 6000},
])
def test_typed_timing_edits_fail_closed(invalid):
    docs, original = source()
    with pytest.raises(StudioQuestError):
        compile_edit(docs, original, invalid)


def test_multiple_timing_edits_keep_monotonic_cues():
    docs, original = source()
    receipt = compile_edit(docs, original, {"1": 1000, "2": 30000})
    assert receipt["timeline"][0]["end_ms"] == 1000
    assert receipt["timeline"][1]["start_ms"] == 1000
    assert receipt["timeline"][1]["end_ms"] == 31000
    for previous, current in zip(receipt["timeline"], receipt["timeline"][1:]):
        assert previous["end_ms"] == current["start_ms"]
    assert receipt["synthetic_duration_ms"] == receipt["timeline"][-1]["end_ms"]


def test_jeeves_contract_returns_canonical_source_leased_review():
    _, original = source()
    request = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_quest_source_digest": original["source_digest"],
        "edits_ms": {"1": 5000}, "format": "html",
    }
    assert caption_timing_tool_schema()["parameters"]["additionalProperties"] is False
    with pytest.raises(PermissionError):
        execute_caption_timing_tool(request)
    result = execute_caption_timing_tool(request, authorized=True)
    assert result["content"].startswith("<!doctype html>")
    assert "script-src" not in result["content"]
    assert "default-src &#x27;none&#x27;" in result["content"]
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert result["content_sha256"] == sha256(result["content"].encode()).hexdigest()
    with pytest.raises(StudioQuestError):
        execute_caption_timing_tool({**request, "format": "wav"}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_caption_timing_tool({**request, "extra": True}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_caption_timing_tool({
            **request, "expected_quest_source_digest": "0" * 64}, authorized=True)


def test_static_html_escapes_authored_markup_and_never_runs_script():
    docs, original = source()
    docs["narrative"]["premise"] = "<img src=x onerror=alert(1)>"
    changed = compile_caption_timing_edit(
        docs, {"1": 5000}, authorized=True,
        expected_source_digest=compile_story_accessibility(
            docs, authorized=True)["source_digest"])
    html = render_caption_timing_review_html(
        docs, changed, authorized=True,
        expected_source_digest=changed["source_digest"]).decode()
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html
    assert "<script" not in html
    assert "default-src" in html
    assert "audio" in html


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-private file custody")
def test_cli_private_source_lease_publication_and_no_clobber(
    tmp_path, monkeypatch, capsys,
):
    _, original = source()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "edits.json").write_text('{"1":5000}')
    (tmp_path / "edits.json").chmod(0o600)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", original["source_digest"],
        "--edits-file", "edits.json",
        "--format", "webvtt", "--output-file", "edited.vtt",
        "--trusted-local-operator",
    ]
    assert main(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["saved_new_private_file"] is True
    assert receipt["audio_sync_verified"] is False
    assert (tmp_path / "edited.vtt").stat().st_mode & 0o077 == 0
    assert (tmp_path / "edited.vtt").read_text().startswith("WEBVTT")
    assert main(args) == 2
    assert "error:" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["edited.vtt", "edits.json"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow file custody")
def test_cli_rejects_duplicate_json_symlink_and_stale_source(
    tmp_path, monkeypatch, capsys,
):
    _, original = source()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    edit = tmp_path / "edits.json"
    edit.write_text('{"1":5000,"1":6000}')
    edit.chmod(0o600)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", original["source_digest"],
        "--edits-file", "edits.json",
        "--format", "html", "--output-file", "review.html",
        "--trusted-local-operator",
    ]
    assert main(args) == 2
    assert not (tmp_path / "review.html").exists()
    edit.unlink()
    edit.symlink_to(tmp_path / "missing.json")
    assert main(args) == 2
    edit.unlink()
    edit.write_text('{"1":5000}')
    edit.chmod(0o600)
    args[args.index(original["source_digest"])] = "0" * 64
    assert main(args) == 2
    assert not (tmp_path / "review.html").exists()

def test_world_router_exposes_typed_caption_editor_only_with_authoring_opt_in():
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        world_tool_catalog, route_world_tool,
    )
    _, original = source()
    names = {item["name"]: item for item in world_tool_catalog()["tools"]}
    assert "studio_original_caption_timing" in names
    assert names["studio_original_caption_timing"][
        "explicit_authoring_permission_required"] is True
    request = {
        "tool": "studio_original_caption_timing",
        "arguments": {
            "schema": REQUEST_SCHEMA, "project_id": PROJECT,
            "expected_quest_source_digest": original["source_digest"],
            "edits_ms": {"1": 5000}, "format": "webvtt",
        },
    }
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    routed = route_world_tool(request, authorized=True, allow_authoring=True)
    assert routed["result"]["content"].startswith("WEBVTT")
    assert routed["result"]["file_write_performed"] is False
    assert routed["release_certified"] is False
    with pytest.raises(StudioQuestError):
        route_world_tool({
            **request, "arguments": {**request["arguments"], "authorized": True},
        }, authorized=True, allow_authoring=True)
