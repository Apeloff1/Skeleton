"""Portable gameplay replay plus real libnx/wut source production boundaries."""
from __future__ import annotations
import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
import pytest
from skeleton.ai.webcrawler.dragon_native_switch_wiiu import original_nintendo_source
from skeleton.ai.webcrawler.dragon_native_projects import (
    render_native_project,EMITTERS,
)
from skeleton.ai.webcrawler.dragon_native_targets import CATALOG,target_catalog
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_platform_readiness import (
    SOURCE_RENDERERS,coverage_report,readiness_for,
)
from skeleton.ai.webcrawler.dragon_compatible_revisions import COMPATIBILITY

TARGETS=("nintendo_switch","wii_u")
REVISIONS=("nintendo_switch_lite","nintendo_switch_oled")

def project(target:str):
    return render_native_project(
        title="Original Dragon Crystal Chapters",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(("native-"+target).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )

@pytest.mark.parametrize("target",TARGETS)
def test_real_console_runtime_source_with_no_fake_executable(target):
    result=project(target)
    assert result.status=="source_generated"
    assert result.target_id==target
    assert "dragon-native-manifest.json" in result.files
    assert "dragon-hardware-budget.json" in result.files
    assert "README.port.md" in result.files
    assert not any(f.endswith((".nro",".rpx",".wuhb")) for f in result.files)
    assert result==project(target)
    prefix="source/" if target=="nintendo_switch" else "src/"
    assert prefix+"main.c" in result.files
    assert prefix+"dragon_game.c" in result.files
    assert prefix+"dragon_game.h" in result.files
    assert "dragon_selftest(void)" in result.files[prefix+"dragon_game.c"]
    assert "dragon_step(" in result.files[prefix+"main.c"]
    assert "step_rng(" in result.files[prefix+"dragon_game.c"]
    assert "dragon_tile(" in result.files[prefix+"main.c"]
    m=json.loads(result.files["dragon-native-manifest.json"])
    assert m["target"]==target and m["status"]=="source_generated"
    assert m["runtime_gameplay_mode"]=="original_collectible_chase"
    assert readiness_for(target).source_emitter
    assert not readiness_for(target).compiler_verified
    assert result.output==("nro" if target=="nintendo_switch" else "rpx")
    assert target in EMITTERS
    assert target in SOURCE_RENDERERS
    assert target in CATALOG
    assert next(x for x in target_catalog() if x["id"]==target)["supported_styles"]==(
        "arcade_score_attack",)

def test_switch_real_libnx_controller_and_nro_makefile():
    p=project("nintendo_switch")
    c=p.files["source/main.c"]
    for token in (
        "#include <switch.h>","padConfigureInput(1,HidNpadStyleSet_NpadStandard)",
        "padInitializeDefault(&pad)","padUpdate(&pad)",
        "padGetButtonsDown(&pad)","padGetButtons(&pad)",
        "HidNpadButton_Plus","HidNpadButton_Up","HidNpadButton_A",
        "consoleInit(NULL)","consoleUpdate(NULL)","consoleExit(NULL)",
        "appletMainLoop()","svcSleepThread(16000000L)",
    ):
        assert token in c
    mk=p.files["Makefile"]
    assert "include $(DEVKITPRO)/libnx/switch_rules" in mk
    assert "ARCH := -march=armv8-a" in mk
    assert "$(OUTPUT).nro" in mk
    assert "dragon_game.o" in mk
    assert "-lnx" in mk
    assert "WIIU" not in c

def test_wiiu_native_gamepad_both_screens_and_wut_rpx():
    p=project("wii_u")
    c=p.files["src/main.c"]
    for token in (
        "#include <vpad/input.h>","#include <coreinit/screen.h>",
        "WHBProcInit()","WHBProcIsRunning()","WHBProcShutdown()",
        "OSScreenGetBufferSizeEx(SCREEN_DRC)",
        "OSScreenGetBufferSizeEx(SCREEN_TV)","OSScreenSetBufferEx",
        "OSScreenPutFontEx(SCREEN_DRC","OSScreenPutFontEx(SCREEN_TV",
        "VPADRead(VPAD_CHAN_0","VPAD_BUTTON_RIGHT","VPAD_BUTTON_X",
        "DCFlushRange(","OSScreenFlipBuffersEx(SCREEN_TV)",
        "OSScreenFlipBuffersEx(SCREEN_DRC)","OSScreenShutdown()",
    ):
        assert token in c
    cmake=p.files["CMakeLists.txt"]
    assert "wut_create_rpx(dragon_original)" in cmake
    assert "src/dragon_game.c" in cmake
    assert "NOT COMMAND wut_create_rpx" in cmake
    assert "Makefile" not in p.files
    assert "wuhb" not in cmake
    assert "RPX" in p.files["README.port.md"]

@pytest.mark.parametrize("target",REVISIONS)
def test_switch_revision_reuses_abi_without_new_binary_claims(target):
    assert target in COMPATIBILITY
    result=project(target)
    assert result.status=="source_generated"
    assert result.output=="nro"
    assert "dragon-compatible-revision.json" in result.files
    assert "source/dragon_game.c" in result.files
    report=json.loads(result.files["dragon-compatible-revision.json"])
    assert report["target"]==target
    assert report["parent"]=="nintendo_switch"
    assert report["target_compiler_verified"] is False
    assert report["target_emulator_verified"] is False
    assert report["target_hardware_verified"] is False
    assert report["native_source_reused_without_binary_substitution"] is True
    manifest=json.loads(result.files["dragon-native-manifest.json"])
    assert manifest["target"]==target
    assert manifest["source_parent"]=="nintendo_switch"
    assert result.target_id==target
    assert target in EMITTERS

def test_switch2_remains_licensed_and_no_fake_new_abi():
    assert CATALOG["nintendo_switch_2"].status=="licensed_sdk"
    assert "nintendo_switch_2" not in EMITTERS
    with pytest.raises(PermissionError,match="licensed"):
        project("nintendo_switch_2")
    with pytest.raises(ValueError):
        original_nintendo_source("nintendo_switch_2",2)

def test_bounded_seed_and_style_contracts():
    for target in TARGETS:
        assert original_nintendo_source(target,1)!=original_nintendo_source(target,2)
        for invalid in (True,-1,2**32,"not uint32",0.5):
            with pytest.raises(ValueError):
                original_nintendo_source(target,invalid)
        with pytest.raises(ValueError,match="gameplay style"):
            render_native_project(
                title="Original Dragon Crystal Chapters",target_id=target,
                style="grand_strategy",candidate_id="a"*64,
                mechanics=(Mechanic.MOVEMENT,),authorized=True)
    report=coverage_report()
    assert report["catalog_count"]==169
    assert report["native_source_count"]==84
    assert report["missing_native_source_count"]==85
    assert len(report["source_ids"])==84

@pytest.mark.parametrize("target",TARGETS)
def test_real_portable_c_gameplay_compilation_and_four_chapter_replay(tmp_path,target):
    if not shutil.which("cc"):
        pytest.skip("host C99 compiler unavailable")
    files=original_nintendo_source(target,365)
    prefix="source/" if target=="nintendo_switch" else "src/"
    core=tmp_path/"dragon_game.c"
    header=tmp_path/"dragon_game.h"
    core.write_text(files[prefix+"dragon_game.c"],encoding="utf-8")
    header.write_text(files[prefix+"dragon_game.h"],encoding="utf-8")
    (tmp_path/"check.c").write_text(
       '#include "dragon_game.h"\n'
       '#include <stdio.h>\n'
       'int main(void){int code=dragon_selftest();'
       'printf("DRAGON_PORTABLE_CHAPTER_REPLAY %s\\n",code?"FAIL":"PASS");'
       'return code;}\n',encoding="utf-8")
    compiled=subprocess.run(
      ["cc","-std=c99","-O2","-Wall","-Wextra","-Werror",
       str(core),str(tmp_path/"check.c"),"-o",str(tmp_path/"check")],
      timeout=40,capture_output=True,text=True)
    assert compiled.returncode==0,(compiled.stdout,compiled.stderr)
    run=subprocess.run([str(tmp_path/"check")],timeout=8,
                       capture_output=True,text=True)
    assert run.returncode==0,(run.stdout,run.stderr)
    assert "DRAGON_PORTABLE_CHAPTER_REPLAY PASS" in run.stdout
