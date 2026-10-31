"""Actual Godot scene compilation, source closure and optional engine startup."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionError, ExpeditionWeather, Traveler,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_godot import (
    emit_expedition_godot_project, attach_expedition_godot_project,
    verify_expedition_godot_project,
)
from skeleton.forge.game_frontier_studio import compile_studio_expedition
from tests.test_game_frontier_expedition_studio import project

SOURCE = "f"*64


def world(seed=99):
    return author_archipelago("native_expedition",SOURCE,
        ArchipelagoProfile(seed=seed,islands=9))


def traveler():
    return Traveler(
        permitted_modes=frozenset((
            "walk","rope_bridge","updraft","glide","airship",
            "portal","climb","dive","swim",
        )),
        flags=frozenset((
            "glider","airship_license","diving_gear","portal_key",
        )),
        equipment=frozenset(("instrument_navigation",)),
        max_stamina=1000,skill=.8,
    )


def test_full_native_godot4_project_has_real_scene_script_and_game_resources():
    w=world();p=traveler()
    files=emit_expedition_godot_project(w,p)
    assert len(files)==6
    assert "project.godot" in files
    assert 'run/main_scene="res://game/frontier/expedition.tscn"' in files["project.godot"]
    assert 'script = ExtResource("1")' in files["game/frontier/expedition.tscn"]
    script=files["game/frontier/expedition.gd"]
    for executable in (
        "func _ready()", "func _setup_scene()", "func _travel(",
        "func _rest()", "func _edge_cost(", "func _can_travel(",
        "func _unhandled_input(", "func _emit_observation(",
        "func _refresh_ui()",
    ):
        assert executable in script
    assert "EXPEDITION_READY" in script
    assert "EXPEDITION_OBSERVATION" in script
    assert "SphereMesh.new()" in script
    assert "ImmediateMesh.new()" in script
    assert "Camera3D.new()" in script
    source=json.loads(files["game/frontier/expedition.json"])
    assert source["source"]==SOURCE
    assert source["project"]=="native_expedition"
    assert len(source["edges"])>10
    assert any(n["kind"]=="sky_island" for n in source["waypoints"])
    assert source["device_location_used"] is False
    assert json.loads(files["game/frontier/player.json"])["max_stamina"]==1000


def test_reproducible_engine_resources_have_verified_source_hashes():
    w=world();p=traveler()
    first=emit_expedition_godot_project(w,p)
    second=emit_expedition_godot_project(world(),traveler())
    assert first==second
    proof=verify_expedition_godot_project(first,w,p)
    assert proof["asset_count"]==6
    assert len(proof["file_hashes"])==6
    assert len(proof["receipt_digest"])==64
    assert not proof["native_playthrough_verified"]


def test_source_or_script_tampering_blocks_game_project_admission():
    w=world();p=traveler()
    files=emit_expedition_godot_project(w,p)
    changed=dict(files)
    changed["game/frontier/expedition.gd"]+="\n# unaudited code\n"
    with pytest.raises(ExpeditionError,match="differs"):
        verify_expedition_godot_project(changed,w,p)
    changed=dict(files)
    data=json.loads(changed["game/frontier/expedition.json"])
    data["source"]="0"*64
    changed["game/frontier/expedition.json"]=json.dumps(data)
    with pytest.raises(ExpeditionError,match="differs"):
        verify_expedition_godot_project(changed,w,p)


def test_changed_traveler_or_weather_cannot_reuse_native_candidate_receipt():
    w=world();p=traveler()
    files=emit_expedition_godot_project(w,p)
    with pytest.raises(ExpeditionError,match="differs"):
        verify_expedition_godot_project(
            files,w,replace(p,max_stamina=999),
        )
    altered=replace(w,weather=ExpeditionWeather(rain=.7))
    with pytest.raises(ExpeditionError,match="differs"):
        verify_expedition_godot_project(files,altered,p)


def test_attach_preserves_existing_native_assets_and_refuses_overwrites():
    w=world();p=traveler()
    existing={"res://studio/hero.gd":"extends CharacterBody3D\n"}
    merged=attach_expedition_godot_project(existing,w,p)
    assert merged["res://studio/hero.gd"]==existing["res://studio/hero.gd"]
    assert "project.godot" not in merged
    assert "game/frontier/expedition.tscn" in merged
    with pytest.raises(ExpeditionError,match="overwritten"):
        attach_expedition_godot_project(
            {"game/frontier/expedition.gd":"extends Node\n"},
            w,p,
        )


def test_studio_export_includes_native_files_by_default():
    data=compile_studio_expedition(
        project(),ArchipelagoProfile(seed=44,islands=7),playtest_routes=3,
    )
    files=data["godot_project_files"]
    assert "project.godot" in files
    assert files["game/frontier/expedition.gd"].startswith("extends Node3D")
    assert data["godot_candidate_proof"]["asset_count"]==6
    assert not data["native_playtest_completed"]
    assert data["world_digest"]==data["godot_candidate_proof"]["world_digest"]


def test_studio_can_explicitly_disable_godot_files_without_fake_run():
    data=compile_studio_expedition(
        project(),ArchipelagoProfile(seed=4,islands=7),include_godot=False,
    )
    assert "godot_project_files" not in data
    assert "godot_candidate_proof" not in data
    assert not data["native_playtest_completed"]


@pytest.mark.parametrize("bad",(1,"true",None))
def test_export_flag_requires_boolean(bad):
    with pytest.raises(ValueError,match="explicit"):
        emit_expedition_godot_project(world(),traveler(),include_project_config=bad)


def test_godot_headless_loads_real_scene_when_binary_available(tmp_path):
    executable=shutil.which("godot4") or shutil.which("godot")
    if executable is None:
        pytest.skip("native Godot 4 executable not installed in test environment")
    files=emit_expedition_godot_project(world(),traveler())
    for path,content in files.items():
        destination=tmp_path/path
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(content,encoding="utf-8")
    run=subprocess.run(
        [executable,"--headless","--path",str(tmp_path),
         "--quit-after","8"],
        cwd=tmp_path,timeout=45,
        capture_output=True,text=True,check=False,
    )
    assert run.returncode==0,run.stdout[-2000:]+run.stderr[-2000:]
    assert "EXPEDITION_READY" in run.stdout,run.stdout[-2000:]
    assert "EXPEDITION_OBSERVATION" in run.stdout
    from skeleton.jeeves.game_frontier_expedition_native_verify import (
        inspect_native_expedition_trace,
    )
    replay=inspect_native_expedition_trace(run.stdout,world(),traveler())
    assert replay["verified_source_gameplay"]
    assert replay["observations"]>=1
