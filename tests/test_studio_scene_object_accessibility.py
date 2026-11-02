"""Scene object labels: source custody, authoring, private CLI, Jeeves and UI."""
from __future__ import annotations

from hashlib import sha256
import copy
import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene import scene_catalog
from skeleton.ai.game_builder.studio_ecosystem_story_html import render_story_html
from skeleton.ai.game_builder.studio_scene_object_accessibility import (
    REQUEST_SCHEMA as SOURCE_REQUEST_SCHEMA,
    compile_scene_object_accessibility, replay_scene_object_accessibility,
    render_scene_object_accessibility_html,
)
from skeleton.ai.agents.jeeves.studio_scene_object_accessibility_tool import (
    REQUEST_SCHEMA, execute_scene_object_accessibility_tool,
    scene_object_accessibility_tool_schema,
)
from skeleton.ai.game_builder.studio_scene_object_accessibility_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    from skeleton.ai.game_builder.studio_ecosystem_quest import compile_quest_program
    program = compile_quest_program(docs)
    scene = scene_catalog(docs)[0]
    labels = {key: "Original scene object: " + key for key in scene["objects"]}
    return docs, program.source_digest, scene, labels


def compile_labels(docs, source, scene, labels):
    return compile_scene_object_accessibility(
        docs, {
            "schema": SOURCE_REQUEST_SCHEMA, "scene_id": scene["scene_id"],
            "labels": labels,
        }, authorized=True, expected_source_digest=source)


def test_exact_canonical_scene_object_coverage_and_playable_compiler():
    docs, source, scene, labels = fixture()
    receipt = compile_labels(docs, source, scene, labels)
    assert receipt == compile_labels(docs, source, scene, labels)
    assert receipt["object_count"] == len(scene["objects"])
    assert [row["object_id"] for row in receipt["objects"]] == list(scene["objects"])
    assert receipt["sandbox_playable_html_compiled"] is True
    assert receipt["sandbox_playable_html_sha256"] == sha256(render_story_html(docs)).hexdigest()
    assert receipt["source_object_coverage_complete"] is True
    assert receipt["asset_rendered"] is False
    assert receipt["accessibility_device_verified"] is False
    assert receipt["release_certified"] is False
    assert replay_scene_object_accessibility(
        docs, receipt, authorized=True, expected_source_digest=source) == receipt


def test_missing_extra_and_forged_scene_object_labels_fail_closed():
    docs, source, scene, labels = fixture()
    missing = dict(labels)
    missing.pop(next(iter(missing)))
    with pytest.raises(StudioQuestError):
        compile_labels(docs, source, scene, missing)
    with pytest.raises(StudioQuestError):
        compile_labels(docs, source, scene, {**labels, "forged_object": "Forged"})
    receipt = compile_labels(docs, source, scene, labels)
    forged = copy.deepcopy(receipt)
    forged["objects"][0]["description"] = "Changed without canonical authoring"
    with pytest.raises(StudioQuestError, match="replay"):
        replay_scene_object_accessibility(
            docs, forged, authorized=True, expected_source_digest=source)
    forged = copy.deepcopy(receipt)
    forged["rights_verified"] = True
    with pytest.raises(StudioQuestError):
        replay_scene_object_accessibility(
            docs, forged, authorized=True, expected_source_digest=source)


@pytest.mark.parametrize("bad", [
    None, 123, True, "", " ", "bad\nline", "x" * 241,
])
def test_invalid_description_values_rejected(bad):
    docs, source, scene, labels = fixture()
    invalid = dict(labels)
    invalid[next(iter(invalid))] = bad
    with pytest.raises(StudioQuestError):
        compile_labels(docs, source, scene, invalid)


def test_authorization_stale_source_and_unregistered_scene_rejected():
    docs, source, scene, labels = fixture()
    with pytest.raises(PermissionError):
        compile_scene_object_accessibility(
            docs, {
                "schema": SOURCE_REQUEST_SCHEMA, "scene_id": scene["scene_id"],
                "labels": labels,
            }, authorized=False, expected_source_digest=source)
    with pytest.raises(StudioQuestError, match="stale"):
        compile_scene_object_accessibility(
            docs, {
                "schema": SOURCE_REQUEST_SCHEMA, "scene_id": scene["scene_id"],
                "labels": labels,
            }, authorized=True, expected_source_digest="0" * 64)
    with pytest.raises(StudioQuestError):
        compile_scene_object_accessibility(
            docs, {
                "schema": SOURCE_REQUEST_SCHEMA, "scene_id": "unknown_scene",
                "labels": labels,
            }, authorized=True, expected_source_digest=source)


def test_html_review_escapes_untrusted_descriptions_and_uses_strict_csp():
    docs, source, scene, labels = fixture()
    labels[next(iter(labels))] = "<svg onload=alert(1)>"
    receipt = compile_labels(docs, source, scene, labels)
    html = render_scene_object_accessibility_html(
        docs, receipt, authorized=True,
        expected_source_digest=source).decode()
    assert "<svg onload" not in html
    assert "&lt;svg onload" in html
    assert "default-src &#x27;none&#x27;" in html
    assert "<script" not in html


def test_typed_jeeves_router_requires_out_of_band_authoring_opt_in():
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool, world_tool_catalog,
    )
    _, source, scene, labels = fixture()
    req = {
        "schema": REQUEST_SCHEMA, "project_id": PROJECT,
        "expected_quest_source_digest": source,
        "scene_id": scene["scene_id"], "labels": labels, "format": "json",
    }
    assert scene_object_accessibility_tool_schema()["parameters"][
        "additionalProperties"] is False
    with pytest.raises(PermissionError):
        execute_scene_object_accessibility_tool(req)
    direct = execute_scene_object_accessibility_tool(req, authorized=True)
    assert direct["asset_rendered"] is False
    assert direct["file_write_performed"] is False
    names = {row["name"]: row for row in world_tool_catalog()["tools"]}
    assert names["studio_original_scene_object_accessibility"][
        "explicit_authoring_permission_required"] is True
    with pytest.raises(PermissionError):
        route_world_tool({"tool": "studio_original_scene_object_accessibility",
                          "arguments": req}, authorized=True)
    routed = route_world_tool({
        "tool": "studio_original_scene_object_accessibility",
        "arguments": req,
    }, authorized=True, allow_authoring=True)
    assert routed["result"] == direct
    with pytest.raises(StudioQuestError):
        execute_scene_object_accessibility_tool(
            {**req, "release_certified": True}, authorized=True)


@pytest.mark.skipif(os.name != "posix", reason="POSIX private file custody")
def test_cli_private_save_restore_no_clobber(tmp_path, monkeypatch, capsys):
    _, source, scene, labels = fixture()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    request_file = tmp_path / "labels.json"
    request_file.write_text(json.dumps({
        "scene_id": scene["scene_id"], "labels": labels,
    }))
    request_file.chmod(0o600)
    args = [
        "--project-id", PROJECT, "--quest-source-digest", source,
        "--request-file", "labels.json", "--format", "json",
        "--output-file", "receipt.json", "--trusted-local-operator",
    ]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["saved_new_private_file"] is True
    assert (tmp_path / "receipt.json").stat().st_mode & 0o077 == 0
    assert main(args) == 2
    assert "error:" in capsys.readouterr().err
    restored = [
        "--project-id", PROJECT, "--quest-source-digest", source,
        "--restore-file", "receipt.json", "--format", "html",
        "--output-file", "review.html", "--trusted-local-operator",
    ]
    assert main(restored) == 0
    assert (tmp_path / "review.html").read_text().startswith("<!doctype html>")


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_cli_rejects_duplicate_keys_symlink_and_stale_source(
    tmp_path, monkeypatch,
):
    _, source, scene, labels = fixture()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    request_file = tmp_path / "labels.json"
    request_file.write_text('{"scene_id":"a","scene_id":"b","labels":{}}')
    request_file.chmod(0o600)
    args = [
        "--project-id", PROJECT, "--quest-source-digest", source,
        "--request-file", "labels.json", "--format", "html",
        "--output-file", "review.html", "--trusted-local-operator",
    ]
    assert main(args) == 2
    request_file.unlink()
    request_file.symlink_to(tmp_path / "missing")
    assert main(args) == 2
    request_file.unlink()
    request_file.write_text(json.dumps({
        "scene_id": scene["scene_id"], "labels": labels,
    }))
    request_file.chmod(0o600)
    args[args.index(source)] = "0" * 64
    assert main(args) == 2
    assert not (tmp_path / "review.html").exists()
