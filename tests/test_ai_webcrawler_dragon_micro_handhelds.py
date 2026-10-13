"""Real micro-handheld original native source and build-boundary checks."""
from __future__ import annotations
import json
import os
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import pytest

from skeleton.ai.webcrawler.dragon_native_playdate import playdate_source
from skeleton.ai.webcrawler.dragon_native_arduboy import arduboy_source
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_native_projects import (
    EMITTERS,render_native_project,
)
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

SOURCES={"playdate":playdate_source,"arduboy":arduboy_source}

@pytest.mark.parametrize("target",("playdate","arduboy"))
def test_original_native_handheld_source_is_deterministic_and_seeded(target):
    func=SOURCES[target]
    assert func(17)==func(17)
    assert func(17)!=func(18)
    for bad in (True,-1,2**32,1.5,"not-seed",None):
        with pytest.raises(ValueError):
            func(bad)
    files=func(5)
    assert files["README.port.md"]
    assert "CMakeLists.txt" not in files if target=="arduboy" else "CMakeLists.txt" in files
    assert "src/main.cpp" in files if target=="arduboy" else "src/main.c" in files
    assert not any(x.endswith((".pdx",".hex")) for x in files)
    assert target in EMITTERS
    record=readiness_for(target)
    assert record.source_emitter
    assert record.claimed_stage=="native_source_generated"
    assert not record.compiler_verified
    assert not record.controller_replay_verified
    assert not record.physical_hardware_verified

def test_playdate_real_buttons_crank_lcd_and_sdk_build_not_lua():
    files=playdate_source(99)
    c=files["src/main.c"]
    for word in ("pd_api.h","PlaydateAPI","PDSystemEvent","kEventInit",
                 "setUpdateCallback","getButtonState","getCrankChange",
                 "setRefreshRate(30)","kButtonLeft","kButtonRight","kButtonA",
                 "kButtonB","kColorWhite","fillRect","score++","hp--",
                 "level=1+score/5"):
        assert word in c
    assert "SDL" not in c and "lua" not in c.lower()
    build=files["CMakeLists.txt"]
    assert "playdate_game.cmake" in build
    assert "PLAYDATE_SDK_PATH" in build
    assert "armgcc" in build and "SHARED" in build
    assert files["Source/pdxinfo"].count("bundleID=")==1

def test_arduboy_bounded_atmega32u4_genuine_oled_and_buttons():
    files=arduboy_source(33)
    source=files["src/main.cpp"]
    for word in ("#include <Arduboy2.h>","Arduboy2 arduboy",
                 "nextFrame()","pollButtons()","setFrameRate(30)",
                 "LEFT_BUTTON","RIGHT_BUTTON","A_BUTTON","B_BUTTON",
                 "drawRect","fillRect","drawPixel","F(","score++","hp--"):
        assert word in source
    assert "malloc" not in source and "new " not in source
    assert "HTML" not in source and "SDL" not in source
    cfg=files["platformio.ini"]
    assert "board = arduboy" in cfg and "platform = atmelavr" in cfg
    assert "MLXXXp/Arduboy2" in cfg

@pytest.mark.parametrize("target,ext",(("playdate","pdx"),("arduboy","hex")))
def test_handheld_source_in_first_class_game_forge_and_rejects_fake_genres(target,ext):
    project=render_native_project(
        title="Original Dragon Tiny Handheld",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    assert project.output==ext
    assert project.status=="source_generated"
    assert project.target_id==target
    assert project==render_native_project(
        title="Original Dragon Tiny Handheld",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True)
    evidence=json.loads(project.files["dragon-native-manifest.json"])
    assert evidence["status"]=="source_generated"
    assert evidence["target"]==target
    assert not any(n.startswith("build/") for n in project.files)
    row=next(t for t in target_catalog() if t["id"]==target)
    assert row["status"]=="native_source"
    assert row["supported_styles"]==("arcade_score_attack",)
    with pytest.raises(ValueError):
        render_native_project(
            title="Original Dragon Tiny Handheld",target_id=target,
            style="grand_strategy",candidate_id="a"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_playdate_sdk_compile_only_if_authorized_toolchain_is_preinstalled(tmp_path):
    if not os.getenv("DRAGON_RUN_MICRO_SDK_BUILD"):
        pytest.skip("opt-in Playdate licensed SDK / toolchain build")
    sdk=os.environ.get("PLAYDATE_SDK_PATH")
    if not sdk or not Path(sdk,"C_API/buildsupport/playdate_game.cmake").is_file():
        pytest.skip("Playdate SDK not installed")
    if not shutil.which("cmake"):
        pytest.skip("CMake not installed")
    root=tmp_path/"playdate"
    for name,data in playdate_source(6).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    subprocess.run(["cmake","-S",str(root),"-B",str(root/"build")],
                   check=True,capture_output=True,text=True,timeout=90)
    subprocess.run(["cmake","--build",str(root/"build")],
                   check=True,capture_output=True,text=True,timeout=120)
    assert (root/"DragonCrank.pdx").exists()

def test_arduboy_sdk_compile_only_if_opted_in(tmp_path):
    if not os.getenv("DRAGON_RUN_MICRO_SDK_BUILD") or not shutil.which("pio"):
        pytest.skip("opt-in local Arduino/Arduboy2 toolchain unavailable")
    root=tmp_path/"arduboy"
    for name,data in arduboy_source(6).items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    subprocess.run(["pio","run","-d",str(root),"-e","arduboy"],check=True,
                   capture_output=True,text=True,timeout=180)
    assert (root/".pio/build/arduboy/firmware.hex").is_file()
