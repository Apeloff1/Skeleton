"""Native checkpoint durability: two slots, campaign-bound CRC32 and native runner."""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project


def _project():
    return render_native_project(
        title="Dragon Save Journey",target_id="pc_linux",
        style="top_down_adventure",candidate_id=sha256(b"save-campaign").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )


def test_source_contains_two_slot_campaign_bound_crc_and_full_compiler_inputs():
    p=_project()
    assert "include/dragon_save.h" in p.files
    assert "src/dragon_save.c" in p.files
    assert "src/dragon_save.c" in p.files["CMakeLists.txt"]
    assert "CAMPAIGN_SIGNATURE" in p.files["include/dragon_campaign.h"]
    src=p.files["src/dragon_save.c"]
    assert "crc32(" in src and "save-a.dat" in src and "save-b.dat" in src
    assert "SDL_GetPrefPath" in src
    assert "rd32(bytes+8)!=signature" in src
    assert "rd32(bytes+32)!=crc32(bytes,32)" in src
    assert "result.stage>=(uint32_t)total" in src
    runtime=p.files["src/main.c"]
    assert "dragon_save_checkpoint(" in runtime
    assert "dragon_save_load(" in runtime
    assert 'strcmp(argv[1],"--checkpoint-test")' in runtime
    assert p.files["dragon-generator-evaluation.json"]
    assert json.loads(p.files["dragon-campaign.json"])["stages"]


def test_real_sdl_checkpoint_roundtrip_on_native_runner(tmp_path):
    if not shutil.which("cmake") or not shutil.which("cc") or not shutil.which("pkg-config"):
        pytest.skip("native CMake + C compiler + pkg-config not installed")
    if subprocess.run(["pkg-config","--exists","sdl2"],timeout=10).returncode:
        pytest.skip("SDL2 development headers not installed")
    project=_project()
    root=tmp_path/"native"
    for path,body in project.files.items():
        output=root/path
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(body,encoding="utf-8")
    conf=subprocess.run(["cmake","-S",str(root),"-B",str(root/"build")],
        timeout=45,capture_output=True,text=True)
    assert conf.returncode==0,conf.stderr
    build=subprocess.run(["cmake","--build",str(root/"build"),"-j","2"],
        timeout=60,capture_output=True,text=True)
    assert build.returncode==0,build.stderr
    xdg=tmp_path/"data"
    xdg.mkdir()
    env={**os.environ,"SDL_VIDEODRIVER":"dummy",
         "SDL_AUDIODRIVER":"dummy","XDG_DATA_HOME":str(xdg)}
    native=subprocess.run([str(root/"build/dragon_game"),"--checkpoint-test"],
        timeout=20,capture_output=True,text=True,env=env)
    assert native.returncode==0,(native.stdout,native.stderr)
    assert "DRAGON_NATIVE_SAVE_TEST PASS" in native.stdout
    files=list(xdg.rglob("save-*.dat"))
    assert len(files)==2
    assert all(p.stat().st_size==36 for p in files)
    again=subprocess.run([str(root/"build/dragon_game"),"--checkpoint-test"],
        timeout=20,capture_output=True,text=True,env=env)
    assert again.returncode==0
    # Never infer runtime playability from a persistence round-trip.
