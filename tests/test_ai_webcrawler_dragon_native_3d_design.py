"""Strict editable game designs and actual native first-person output gates."""
from __future__ import annotations
from hashlib import sha256
import json,os,shutil,subprocess
import pytest
from skeleton.ai.webcrawler.dragon_game_design import (
    parse_design,load_design,starter_design,
)
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project


def test_user_editable_design_changes_stages_palette_and_candidate_budget(tmp_path):
    config=starter_design(
        title="Dragon Haunted Labyrinth",target="pc_linux",
        genre="first_person_shooter",seed=1234)
    config["stages"]=6
    config["candidates"]=12
    config["palette"]="crt_arcade"
    config["project_notes"]="Explore and defeat original guardians"
    design=parse_design(config)
    assert design.stages==6 and design.candidates==12 and len(design.digest)==64
    path=tmp_path/"game.json"
    path.write_text(json.dumps(config),encoding="utf-8")
    assert load_design(path)==design
    target=tmp_path/"project"
    emit_demo("unused",target,design=design)
    source=json.loads((target/"dragon-campaign.json").read_text())
    assert len(source["stages"])==6 and source["palette"]=="crt_arcade"
    evaluation=json.loads((target/"dragon-generator-evaluation.json").read_text())
    assert evaluation["candidate_budget"]==12
    recorded=json.loads((target/"dragon-game-design.json").read_text())
    assert recorded["digest"]==design.digest
    assert (target/"src/main.c").is_file()
    assert "DRAGON_RAYCAST_SMOKE" in (target/"src/main.c").read_text()


@pytest.mark.parametrize("field,bad",[
    ("stages",0),("stages",True),("stages",10),("candidates",100),
    ("seed",-1),("seed",2**32),("title","; touch /tmp/hack"),
    ("genre","unrealistic_genre"),("palette","../../../"),("hero","nobody"),
    ("quest_theme","evil<script>"),("project_notes","; rm -rf /"),
])
def test_invalid_design_is_not_rendered_as_executable_source(field,bad):
    fields=starter_design()
    fields[field]=bad
    with pytest.raises(ValueError):
        parse_design(fields)


def test_unknown_schema_fields_and_duplicate_keys_rejected(tmp_path):
    data=starter_design()
    data["command"]="curl attacker"
    with pytest.raises(ValueError):
        parse_design(data)
    path=tmp_path/"bad.json"
    path.write_text('{"seed":1,"seed":2}')
    with pytest.raises(ValueError,match="duplicate"):
        load_design(path)
    with pytest.raises(ValueError):
        parse_design({"target":"pc_linux"})


def test_native_3d_source_has_dda_projection_depth_enemy_and_controller():
    game=render_native_project(title="Original FPS",target_id="pc_linux",
        style="first_person_shooter",candidate_id=sha256(b"fps").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    source=game.files["src/main.c"]
    assert "DRAGON_RAYCAST_SMOKE" in source
    assert "distanceX<distanceY" in source
    assert "float depth=" in source
    assert "depths[c]" in source
    assert "ty<depths[col/2]" in source
    assert "SDL_GameControllerGetButton" in source
    assert "SDL_SCANCODE_RIGHT" in source
    assert "guardians" in source and "has_key" in source
    assert "SDL2::SDL2" in game.files["CMakeLists.txt"]
    campaign=json.loads(game.files["dragon-campaign.json"])
    assert campaign["mode"]=="dungeon"
    assert len(campaign["stages"])==4
    manifest=json.loads(game.files["dragon-native-manifest.json"])
    assert manifest["runtime_gameplay_mode"]=="native_dda_first_person"
    assert "<html" not in source


@pytest.mark.parametrize("genre",["first_person_shooter","immersive_sim"])
def test_real_3d_sdl_binary_build_and_headless_depth_scan(tmp_path,genre):
    if not all(shutil.which(x) for x in ("cmake","cc","pkg-config")):
        pytest.skip("CMake/C compiler unavailable")
    if subprocess.run(["pkg-config","--exists","sdl2"],
        timeout=10,capture_output=True).returncode!=0:
        pytest.skip("SDL2 C headers unavailable")
    config=starter_design(title="Dragon Original FPS",genre=genre,seed=145)
    game=parse_design(config)
    project=tmp_path/genre
    emit_demo("pc_linux",project,design=game)
    c=subprocess.run(["cmake","-S",str(project),"-B",str(project/"build")],
        timeout=40,capture_output=True,text=True)
    assert c.returncode==0,c.stderr
    build=subprocess.run(["cmake","--build",str(project/"build"),"-j","2"],
        timeout=60,capture_output=True,text=True)
    assert build.returncode==0,build.stderr
    run=subprocess.run([str(project/"build/dragon_game"),"--smoke"],
        env={**os.environ,"SDL_VIDEODRIVER":"dummy",
             "SDL_AUDIODRIVER":"dummy"},
        timeout=20,capture_output=True,text=True)
    assert run.returncode==0,(run.stdout,run.stderr)
    assert "DRAGON_RAYCAST_SMOKE PASS" in run.stdout
