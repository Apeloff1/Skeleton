"""Native rhythm stage chart, original audio, perfect-play and miss judging."""
from __future__ import annotations
from hashlib import sha256
import json,os,shutil,subprocess
import pytest
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_game_design import starter_design,parse_design
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog


def project():
    return render_native_project(
        title="Dragon Native Beat Forge",target_id="pc_linux",
        style="rhythm_game",candidate_id=sha256(b"rhythm").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )


def test_native_rhythm_is_mechanical_beat_game_not_regular_arcade_skin():
    result=project()
    source=result.files["src/main.c"]
    header=result.files["include/dragon_rhythm.h"]
    assert result.status=="source_generated"
    assert "DRAGON_RHYTHM_SMOKE" in source
    assert "abs(delta)<=PERFECT_WINDOW" in source
    assert "abs(delta)<=GOOD_WINDOW" in source
    assert "g.miss++" in source
    assert "g.combo++" in source
    assert "g.hp-=7" in source
    assert "g.max_combo" in source
    assert "SDL_QueueAudio" in source
    assert "SDL_CONTROLLER_BUTTON_Y" in source
    assert "#define SONG_COUNT 4" in header
    assert "#define NOTES_PER_SONG 64" in header
    assert "rhythm_charts[SONG_COUNT][NOTES_PER_SONG]" in header
    manifest=json.loads(result.files["dragon-native-manifest.json"])
    assert manifest["runtime_gameplay_mode"]=="native_timing_rhythm"
    assert manifest["campaign_stages"]==4
    assert "dragon-campaign.json" not in result.files
    assert "dragon-generator-evaluation.json" not in result.files
    assert "dragon-playtest-plan.json" not in result.files
    assert json.loads(result.files["dragon-rhythm-production.json"])["notes_per_song"]==64
    assert "rhythm_game" in {t["id"]:t for t in target_catalog()}["pc_linux"]["supported_styles"]


def test_editable_spec_controls_actual_rhythm_judgement_and_songs(tmp_path):
    one=starter_design(title="Dragon Original Music",genre="rhythm_game",seed=2)
    one.update({"difficulty":1,"stages":3})
    a=parse_design(one)
    destination=tmp_path/"rhythm"
    emit_demo("pc_linux",destination,design=a)
    head=(destination/"include/dragon_rhythm.h").read_text()
    assert "#define SONG_COUNT 3" in head
    assert "#define PERFECT_WINDOW 6" in head
    one.update({"difficulty":10,"stages":3})
    b=parse_design(one)
    hard=tmp_path/"hard"
    emit_demo("pc_linux",hard,design=b)
    other=(hard/"include/dragon_rhythm.h").read_text()
    assert "#define PERFECT_WINDOW 2" in other
    assert head!=other
    assert "dragon-native-manifest.json" in [p.name for p in destination.iterdir()]


def test_actual_native_rhythm_compilation_and_deterministic_perfect_play(tmp_path):
    if not all(shutil.which(x) for x in ("cc","cmake","pkg-config")):
        pytest.skip("native compiler and SDL2 prerequisites missing")
    if subprocess.run(["pkg-config","--exists","sdl2"],timeout=10).returncode!=0:
        pytest.skip("SDL2 development headers missing")
    src=project()
    root=tmp_path/"native-rhythm"
    for name,body in src.files.items():
        p=root/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(body,encoding="utf-8")
    cfg=subprocess.run(["cmake","-S",str(root),"-B",str(root/"build")],
        capture_output=True,text=True,timeout=40)
    assert cfg.returncode==0,cfg.stderr
    compile=subprocess.run(["cmake","--build",str(root/"build"),"-j","2"],
        capture_output=True,text=True,timeout=60)
    assert compile.returncode==0,compile.stderr
    runtime=subprocess.run([str(root/"build/dragon_game"),"--smoke"],
        env={**os.environ,"SDL_VIDEODRIVER":"dummy",
             "SDL_AUDIODRIVER":"dummy"},
        capture_output=True,text=True,timeout=20)
    assert runtime.returncode==0,(runtime.stdout,runtime.stderr)
    assert "DRAGON_RHYTHM_SMOKE PASS" in runtime.stdout
    assert "missed=0" in runtime.stdout
