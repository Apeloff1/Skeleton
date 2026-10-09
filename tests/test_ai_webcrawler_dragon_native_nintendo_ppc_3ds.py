"""Open devkitPro native games must use true PPC/ARM11 APIs, not PC shims."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,pytest,shutil,subprocess
from skeleton.ai.webcrawler.dragon_native_nintendo_ppc_3ds import (
    gamecube_source,wii_source,three_ds_source,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project,EMITTERS
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

NEW={"gamecube":"dol","wii":"dol","nintendo_3ds":"3dsx"}

@pytest.mark.parametrize("target,expected",list(NEW.items()))
def test_nintendo_ppc_and_3ds_native_game_project_is_real_target_source(target,expected):
    out=render_native_project(
        title="Original Dragon Open Console",target_id=target,
        style="arcade_score_attack",
        candidate_id=sha256(("original"+target).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    assert out.status=="source_generated"
    assert out.target_id==target and out.output==expected
    assert "src/main.c" in out.files
    assert "Makefile" in out.files
    assert "README.port.md" in out.files
    assert "CMakeLists.txt" not in out.files
    assert not any(p.endswith((".dol",".3dsx")) for p in out.files)
    assert out==render_native_project(
        title="Original Dragon Open Console",target_id=target,
        style="arcade_score_attack",
        candidate_id=sha256(("original"+target).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    info=json.loads(out.files["dragon-native-manifest.json"])
    assert info["status"]=="source_generated"
    assert info["target"]==target
    assert info["runtime_gameplay_mode"]=="original_collectible_chase"
    assert readiness_for(target).source_emitter
    assert not readiness_for(target).compiler_verified
    target_row=next(x for x in target_catalog() if x["id"]==target)
    assert target_row["status"]=="native_source"
    assert target_row["supported_styles"]==("arcade_score_attack",)
    assert target in EMITTERS
    with pytest.raises(ValueError):
        render_native_project(title="Original Dragon Open Console",
            target_id=target,style="grand_strategy",
            candidate_id="a"*64,mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_gamecube_has_real_pad_video_boot_enemy_ai_and_recovery():
    files=gamecube_source(42)
    c=files["src/main.c"]
    for term in ("#include <gccore.h>","VIDEO_Init()","PAD_Init()",
                 "VIDEO_GetPreferredMode","SYS_AllocateFramebuffer",
                 "MEM_K0_TO_K1","console_init(","VIDEO_SetNextFramebuffer",
                 "PAD_ScanPads()","PAD_ButtonsHeld","PAD_BUTTON_START",
                 "VIDEO_WaitVSync()","random_next()","lives--",
                 "score++","enemies"):
        assert term in c
    m=files["Makefile"]
    assert "gamecube_rules" in m
    assert "elf2dol" in m and "-logc" in m
    assert "wiiuse/wpad.h" in c
    assert "DRAGON_WII" not in m

def test_wii_uses_true_wpad_remote_and_gamecube_controller_paths():
    files=wii_source(17)
    c,m=files["src/main.c"],files["Makefile"]
    assert "wii_rules" in m
    assert "-DDRAGON_WII=1" in m
    assert "-lwiiuse" in m and "-lbte" in m
    for term in ("WPAD_Init()","WPAD_ScanPads()","WPAD_ButtonsHeld",
                 "WPAD_ButtonsDown","WPAD_BUTTON_HOME","WPAD_BUTTON_A",
                 "PAD_ScanPads()","VIDEO_WaitVSync()"):
        assert term in c
    assert c!=gamecube_source(17)["src/main.c"]

def test_3ds_has_citro2d_real_gpu_and_touch_screen_aim():
    files=three_ds_source(94)
    c,m=files["src/main.c"],files["Makefile"]
    for term in ("#include <3ds.h>","#include <citro2d.h>",
                 "gfxInitDefault()","consoleInit(GFX_BOTTOM,NULL)",
                 "C3D_Init(C3D_DEFAULT_CMDBUF_SIZE)",
                 "C2D_CreateScreenTarget(GFX_TOP,GFX_LEFT)",
                 "C2D_DrawRectSolid(","C3D_FrameBegin","C3D_FrameEnd",
                 "hidScanInput()","hidKeysHeld()","hidKeysDown()",
                 "hidTouchRead(","KEY_TOUCH","KEY_START","KEY_X",
                 "C2D_Fini()","C3D_Fini()","score++",
                 "hp--","iframes=50"):
        assert term in c
    assert "3ds_rules" in m
    assert "3dsxtool" in m
    assert "-lcitro2d" in m and "-lcitro3d" in m
    assert "-lctru" in m
    assert "Wii" not in c

@pytest.mark.parametrize("maker",[gamecube_source,wii_source,three_ds_source])
def test_seed_contract_is_bounded_and_original(maker):
    assert maker(123)==maker(123)
    assert maker(123)!=maker(124)
    for bad in (-1,2**32,True,2.5,"unsafe"):
        with pytest.raises(ValueError):
            maker(bad)

@pytest.mark.parametrize("target,tool",[
    ("gamecube","powerpc-eabi-gcc"),
    ("wii","powerpc-eabi-gcc"),
    ("nintendo_3ds","arm-none-eabi-gcc"),
])
def test_cross_compile_only_when_actual_sdk_and_toolchain_installed(
    tmp_path,target,tool,monkeypatch,
):
    import os
    if not shutil.which(tool) or not shutil.which("make") or (
        not os.environ.get("DEVKITPRO")
    ) or not os.environ.get("DEVKITPPC" if target!="nintendo_3ds" else "DEVKITARM"):
        pytest.skip("actual devkitPro system SDK and cross compiler missing")
    files=(gamecube_source(17) if target=="gamecube" else
           wii_source(17) if target=="wii" else three_ds_source(17))
    for path,body in files.items():
        dest=tmp_path/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(body)
    result=subprocess.run(["make","-C",str(tmp_path),"all"],timeout=120,
                          capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert (tmp_path/"build"/("dragon.3dsx" if target=="nintendo_3ds"
                             else "dragon.dol")).stat().st_size>0
