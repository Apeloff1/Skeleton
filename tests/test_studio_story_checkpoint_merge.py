"""Source-bound three-way story checkpoint merge regression and custody tests."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source
from skeleton.ai.game_builder.studio_ecosystem_story_merge import (
    merge_browser_story_checkpoints,
)
from skeleton.ai.agents.jeeves.studio_story_merge_tool import (
    REQUEST_SCHEMA, execute_story_merge_tool, story_merge_tool_schema,
)
from skeleton.ai.game_builder.studio_story_checkpoint_merge_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def _receipt(source, actions):
    return json.dumps({
        "schema": "skeleton.game_builder.offline_story_choices.v1",
        "project_id": source["project_id"],
        "source_digest": source["source_digest"],
        "choices": actions,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }, ensure_ascii=True).encode("utf-8")


def _sources():
    documents = read_blueprint(PROJECT)
    return documents, story_source(documents)


def _merge(documents, ancestor, current, candidate, authorized=True):
    return merge_browser_story_checkpoints(
        ancestor, current, candidate, documents, authorized=authorized)


def test_merge_identical_and_fast_forward_checkpoints_replay():
    documents, source = _sources()
    stage = source["stages"][0]
    empty = _receipt(source, [])
    first = _receipt(source, [[stage["id"], stage["alternatives"][0]]])
    result = _merge(documents, empty, empty, first)
    assert result["merged_action_count"] == 1
    assert result["replayed_from_authoritative_source"] is True
    assert result["persisted"] is False
    assert result["release_certified"] is False
    assert json.loads(result["merged_checkpoint"])["choices"] == [
        [stage["id"], stage["alternatives"][0]]]
    assert _merge(documents, empty, first, first)["merged_session_digest"] == (
        result["merged_session_digest"])


def test_merge_conflicts_and_invalid_ancestor_fail_closed():
    documents, source = _sources()
    stage = source["stages"][0]
    assert len(stage["alternatives"]) >= 2
    empty = _receipt(source, [])
    left = _receipt(source, [[stage["id"], stage["alternatives"][0]]])
    right = _receipt(source, [[stage["id"], stage["alternatives"][1]]])
    with pytest.raises(StudioQuestError, match="conflict"):
        _merge(documents, empty, left, right)
    with pytest.raises(StudioQuestError, match="ancestor"):
        _merge(documents, left, empty, right)
    with pytest.raises(PermissionError):
        _merge(documents, empty, left, left, authorized=False)


def test_merge_rejects_forged_release_duplicate_keys_and_stale_source():
    documents, source = _sources()
    empty = _receipt(source, [])
    forged = json.loads(empty)
    forged["release_certified"] = True
    with pytest.raises(StudioQuestError):
        _merge(documents, empty, empty, json.dumps(forged).encode())
    duplicate = empty[:-1] + b', "choices": []}'
    with pytest.raises(StudioQuestError):
        _merge(documents, duplicate, empty, empty)
    stale = json.loads(empty)
    stale["source_digest"] = "0" * 64
    with pytest.raises(StudioQuestError):
        _merge(documents, empty, empty, json.dumps(stale).encode())
    with pytest.raises(StudioQuestError):
        _merge(documents, empty, empty, b"x" * 65537)


def test_typed_jeeves_merge_contract_and_source_lease():
    _, source = _sources()
    empty = _receipt(source, []).decode()
    request = {
        "schema": REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_quest_source_digest": source["source_digest"],
        "ancestor_checkpoint": empty,
        "current_checkpoint": empty,
        "candidate_checkpoint": empty,
    }
    assert story_merge_tool_schema()["parameters"]["additionalProperties"] is False
    with pytest.raises(PermissionError):
        execute_story_merge_tool(request)
    result = execute_story_merge_tool(request, authorized=True)
    assert result["canonical_replay"]["merged_action_count"] == 0
    assert result["file_write_performed"] is False
    assert result["result_digest"]
    with pytest.raises(StudioQuestError):
        execute_story_merge_tool({**request, "authorized": True}, authorized=True)
    with pytest.raises(StudioQuestError):
        execute_story_merge_tool({**request,
            "expected_quest_source_digest": "0" * 64}, authorized=True)


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow fd custody only")
def test_operator_cli_private_atomic_save_no_overwrite(tmp_path, monkeypatch, capsys):
    _, source = _sources()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    stage = source["stages"][0]
    files = {
        "base.json": _receipt(source, []),
        "left.json": _receipt(source, []),
        "right.json": _receipt(source, [[stage["id"], stage["alternatives"][0]]]),
    }
    for name, value in files.items():
        target = tmp_path / name
        target.write_bytes(value)
        target.chmod(0o600)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", source["source_digest"],
        "--ancestor-file", "base.json",
        "--current-file", "left.json",
        "--candidate-file", "right.json",
        "--output-file", "merged.json",
        "--trusted-local-operator",
    ]
    assert main(args) == 0
    proof = json.loads(capsys.readouterr().out)
    assert proof["saved_new_private_file"] is True
    assert json.loads((tmp_path / "merged.json").read_text())["choices"] == [
        [stage["id"], stage["alternatives"][0]]]
    assert (tmp_path / "merged.json").stat().st_mode & 0o077 == 0
    assert main(args) == 2
    assert "error:" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([
        "base.json", "left.json", "right.json", "merged.json"])


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow fd custody only")
def test_operator_cli_rejects_symlinks_world_readable_and_bad_directory(
        tmp_path, monkeypatch):
    _, source = _sources()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    empty = _receipt(source, [])
    for name in ("base.json", "left.json", "right.json"):
        (tmp_path / name).write_bytes(empty)
        (tmp_path / name).chmod(0o600)
    args = [
        "--project-id", PROJECT,
        "--quest-source-digest", source["source_digest"],
        "--ancestor-file", "base.json",
        "--current-file", "left.json",
        "--candidate-file", "right.json",
        "--output-file", "merged.json",
        "--trusted-local-operator",
    ]
    (tmp_path / "right.json").unlink()
    (tmp_path / "right.json").symlink_to(tmp_path / "left.json")
    assert main(args) == 2
    (tmp_path / "right.json").unlink()
    (tmp_path / "right.json").write_bytes(empty)
    (tmp_path / "right.json").chmod(0o644)
    assert main(args) == 2
    (tmp_path / "right.json").chmod(0o600)
    tmp_path.chmod(0o755)
    assert main(args) == 2
    assert not (tmp_path / "merged.json").exists()

def test_world_router_requires_separate_authoring_authority():
    from skeleton.ai.agents.jeeves.studio_world_tool_router import (
        route_world_tool,
    )
    _, source = _sources()
    empty = _receipt(source, []).decode("utf-8")
    request = {
        "tool": "studio_original_story_checkpoint_merge",
        "arguments": {
            "schema": REQUEST_SCHEMA,
            "project_id": PROJECT,
            "expected_quest_source_digest": source["source_digest"],
            "ancestor_checkpoint": empty,
            "current_checkpoint": empty,
            "candidate_checkpoint": empty,
        },
    }
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=False, allow_authoring=True)
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True, allow_authoring=False)
    receipt = route_world_tool(request, authorized=True, allow_authoring=True)
    assert receipt["result"]["canonical_replay"]["merged_action_count"] == 0
    assert receipt["file_write_performed"] is False
    assert receipt["release_certified"] is False

@pytest.mark.skipif(os.name != "posix", reason="POSIX durability barrier only")
def test_private_merge_rolls_back_on_directory_fsync_failure(
        tmp_path, monkeypatch, capsys):
    import stat

    _, source = _sources()
    tmp_path.chmod(0o700)
    monkeypatch.chdir(tmp_path)
    empty = _receipt(source, [])
    for name in ("base.json", "left.json", "right.json"):
        path = tmp_path / name
        path.write_bytes(empty)
        path.chmod(0o600)
    real_fsync = os.fsync

    def fail_directory_barrier(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected directory durability failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_barrier)
    assert main([
        "--project-id", PROJECT,
        "--quest-source-digest", source["source_digest"],
        "--ancestor-file", "base.json",
        "--current-file", "left.json",
        "--candidate-file", "right.json",
        "--output-file", "merged.json",
        "--trusted-local-operator",
    ]) == 2
    assert "error:" in capsys.readouterr().err
    assert not (tmp_path / "merged.json").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "base.json", "left.json", "right.json"]
