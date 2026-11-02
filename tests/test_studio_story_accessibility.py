"""Accessibility reading edition and source-bound WebVTT compilation."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source
from skeleton.ai.game_builder.studio_ecosystem_story_accessibility import (
    compile_story_accessibility,
)
from skeleton.ai.agents.jeeves.studio_story_accessibility_tool import (
    REQUEST_SCHEMA, execute_story_accessibility_tool,
)
from skeleton.ai.game_builder.studio_story_accessibility_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def _source():
    docs = read_blueprint(PROJECT)
    return docs, story_source(docs)


def test_accessible_story_has_every_authored_stage_and_no_audio_claims():
    docs, source = _source()
    first = compile_story_accessibility(docs, authorized=True)
    second = compile_story_accessibility(docs, authorized=True)
    assert first == second
    assert first["source_digest"] == source["source_digest"]
    assert first["stage_count"] == len(source["stages"])
    assert first["caption_count"] == 1 + 2 * len(source["stages"]) + len(source["endings"])
    assert first["webvtt"].startswith("WEBVTT\n\nNOTE")
    assert first["webvtt"].count(" --> ") == first["caption_count"]
    assert first["audio_rendered"] is False
    assert first["audio_sync_verified"] is False
    assert first["release_certified"] is False
    assert first["markdown_sha256"] == sha256(first["markdown"].encode()).hexdigest()
    for stage in source["stages"]:
        assert stage["id"] in first["markdown"]
    with pytest.raises(PermissionError):
        compile_story_accessibility(docs, authorized=False)


def test_accessibility_escapes_untrusted_authored_text_and_fails_closed():
    docs, _ = _source()
    docs["narrative"]["premise"] = "<script>alert(1)</script>"
    compiled = compile_story_accessibility(docs, authorized=True)
    assert "<script>" not in compiled["markdown"]
    assert "&lt;script&gt;" in compiled["markdown"]
    assert "<script>" not in compiled["webvtt"]
    docs["narrative"]["premise"] = "unsafe\ncue"
    with pytest.raises(StudioQuestError):
        compile_story_accessibility(docs, authorized=True)


def test_jeeves_accessibility_is_typed_source_leased_and_read_only():
    _, source = _source()
    request = {
        "schema": REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_quest_source_digest": source["source_digest"],
        "format": "webvtt",
    }
    with pytest.raises(PermissionError):
        execute_story_accessibility_tool(request)
    result = execute_story_accessibility_tool(request, authorized=True)
    assert result["content"].startswith("WEBVTT")
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    with pytest.raises(StudioQuestError):
        execute_story_accessibility_tool({**request, "format": "wav"}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_story_accessibility_tool({**request,
            "expected_quest_source_digest": "0" * 64}, authorized=True)


@pytest.mark.skipif(os.name != "posix", reason="POSIX private publication only")
def test_accessibility_cli_publishes_once_without_overwrite(tmp_path, monkeypatch, capsys):
    _, source = _source()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", source["source_digest"],
        "--format", "webvtt", "--output-file", "story.vtt",
        "--trusted-local-operator",
    ]
    assert main(args) == 0
    proof = json.loads(capsys.readouterr().out)
    assert proof["saved_new_private_file"] is True
    assert (tmp_path / "story.vtt").read_text().startswith("WEBVTT")
    assert (tmp_path / "story.vtt").stat().st_mode & 0o077 == 0
    assert main(args) == 2
    assert "error:" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["story.vtt"]
