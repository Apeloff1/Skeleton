"""Operator CLI exercises the same canonical replay as Jeeves without writes."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source
from skeleton.ai.game_builder.studio_story_checkpoint_cli import main

PROJECT = "studio_arena_fighting_glacial_fjord"


def _checkpoint(source, actions):
    return json.dumps({
        "schema": "skeleton.game_builder.offline_story_choices.v1",
        "project_id": source["project_id"], "source_digest": source["source_digest"],
        "choices": actions, "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    })


def _write_private(path, value):
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def _args(source):
    return [
        "--project-id", PROJECT,
        "--quest-source-digest", source["source_digest"],
        "--checkpoint-file", "current.json",
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow fd custody only")
def test_cli_preview_and_comparison_replay_without_writing(tmp_path, monkeypatch, capsys):
    source = story_source(read_blueprint(PROJECT))
    stage = source["stages"][0]
    monkeypatch.chdir(tmp_path)
    _write_private(tmp_path / "current.json", _checkpoint(source, []))
    _write_private(tmp_path / "candidate.json", _checkpoint(
        source, [[stage["id"], stage["alternatives"][0]]]))
    assert main(_args(source) + [
        "--preview-stage", stage["id"], "--alternative", stage["alternatives"][0]]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["canonical_replay"]["stage_id"] == stage["id"]
    assert preview["file_write_performed"] is False
    assert main(_args(source) + ["--compare-file", "candidate.json"]) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["canonical_replay"]["candidate_only_actions"]
    assert comparison["release_certified"] is False
    assert sorted(p.name for p in tmp_path.iterdir()) == ["candidate.json", "current.json"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow fd custody only")
def test_cli_rejects_symlink_world_readable_and_traversal(tmp_path, monkeypatch, capsys):
    source = story_source(read_blueprint(PROJECT))
    monkeypatch.chdir(tmp_path)
    _write_private(tmp_path / "target.json", _checkpoint(source, []))
    (tmp_path / "current.json").symlink_to(tmp_path / "target.json")
    stage = source["stages"][0]
    preview = ["--preview-stage", stage["id"],
               "--alternative", stage["alternatives"][0]]
    assert main(_args(source) + preview) == 2
    (tmp_path / "current.json").unlink()
    _write_private(tmp_path / "current.json", _checkpoint(source, []))
    (tmp_path / "current.json").chmod(0o644)
    assert main(_args(source) + preview) == 2
    (tmp_path / "current.json").chmod(0o600)
    wrong = _args(source)
    wrong[wrong.index("current.json")] = "../current.json"
    assert main(wrong + preview) == 2
    assert main([part for part in _args(source) if part != "--trusted-local-operator"]
                + preview) == 2
    assert capsys.readouterr().err.count("error:") >= 4


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow fd custody only")
def test_cli_rejects_oversize_and_forged_release(tmp_path, monkeypatch, capsys):
    source = story_source(read_blueprint(PROJECT))
    monkeypatch.chdir(tmp_path)
    stage = source["stages"][0]
    preview = ["--preview-stage", stage["id"],
               "--alternative", stage["alternatives"][0]]
    _write_private(tmp_path / "current.json", "x" * 65537)
    assert main(_args(source) + preview) == 2
    forged = json.loads(_checkpoint(source, []))
    forged["release_certified"] = True
    _write_private(tmp_path / "current.json", json.dumps(forged))
    assert main(_args(source) + preview) == 2
    assert "error:" in capsys.readouterr().err
