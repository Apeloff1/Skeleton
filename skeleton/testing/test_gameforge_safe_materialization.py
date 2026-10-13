"""Fail-closed Godot materialization and required-playtest semantics."""
from __future__ import annotations
import hashlib
import json
from unittest.mock import patch
import pytest
from skeleton.forge.projector import ProjectExistsError, write_project
from skeleton.context.pipeline import _stage_emit

def source():
    return {"project.godot":"[application]\n", "data/rooms.json":"{}"}

@pytest.mark.parametrize("bad",[
    "../evil.gd","/tmp/evil.gd","x/../../evil.gd","C:/evil.gd",
    "data\\evil.gd","data//evil.gd","data/./evil.gd",
    "CON.txt","FORGE_MANIFEST.json","CONTEXT_LEDGER.json","build_report.md",
])
def test_untrusted_paths_rejected_without_writes(tmp_path,bad):
    folder=tmp_path/"game"
    with pytest.raises(ValueError):
        write_project(folder,{**source(),bad:"bad"})
    assert not folder.exists()

def test_manifest_hashes_and_collision_protection(tmp_path):
    root=tmp_path/"game"
    manifest=write_project(root,source())
    assert manifest["sha256"]["project.godot"]==hashlib.sha256(
        source()["project.godot"].encode()).hexdigest()
    assert json.loads((root/"FORGE_MANIFEST.json").read_text())==manifest
    with pytest.raises(ProjectExistsError):
        write_project(root,{"project.godot":"replacement"})
    assert (root/"project.godot").read_text()==source()["project.godot"]

def test_symlink_escape_is_denied_even_with_overwrite(tmp_path):
    outside=tmp_path/"outside"
    outside.mkdir()
    root=tmp_path/"game"
    root.mkdir()
    (root/"data").symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):
        write_project(root,source(),overwrite=True)
    assert list(outside.iterdir())==[]

def test_require_failed_playtest_never_writes_project(tmp_path):
    root=tmp_path/"game"
    with patch("skeleton.forge.gdscript_check.check_ok",return_value=(True, [])):
        with patch("skeleton.forge.playtest.playtest",
                   return_value={"passed":False,"status":"unavailable","reason":"no binary"}):
            with pytest.raises(RuntimeError,match="playtest unavailable"):
                _stage_emit({"files":source(),"era":"soulslike",
                             "project_root":str(root),"playtest_mode":"require"})
    assert not root.exists()

def test_auto_playtest_records_unavailability_but_can_emit(tmp_path):
    root=tmp_path/"game"
    with patch("skeleton.forge.gdscript_check.check_ok",return_value=(True, [])):
        with patch("skeleton.forge.playtest.playtest",
                   return_value={"passed":False,"status":"unavailable"}):
            with patch("skeleton.context.pipeline._commit"):
                report=_stage_emit({"files":source(),"era":"cozy_wholesome",
                                    "cockpit":object(),"project_root":str(root),
                                    "playtest_mode":"auto"})
    assert report["playtest"]["passed"] is False
    assert report["project"]["count"]==2
