"""Actual N64, Nintendo DS and PSP source-generation capability and SDK contracts.

Honest contract: source-only until SDK CI/emulator runs are configured.
Console controller, graphics, rules and build scripts must differ materially.
"""
from __future__ import annotations
from hashlib import sha256
import json
import pytest
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project,EMITTERS
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_3d_era import n64_source,ds_source,psp_source

TARGETS=("nintendo_64","nintendo_ds","psp")

def generate(t:str):
    return render_native_project(
        title="Original Dragon 3D Era",target_id=t,style="arcade_score_attack",
        candidate_id=sha256(t.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )

@pytest.mark.parametrize("t,extension",[
    ("nintendo_64","z64"),("nintendo_ds","nds"),("psp","pbp")
])
def test_era_specific_console_profiles_are_native_sdk_source_only(t,extension):
    assert t in EMITTERS
    p=generate(t)
    assert p.status=="source_generated" and p.output==extension
    assert "src/main.c" in p.files
    assert "Makefile" in p.files
    assert "CMakeLists.txt" not in p.files
    assert p.digest==generate(t).digest
    assert p.files["src/main.c"]==generate(t).files["src/main.c"]
    m=json.loads(p.files["dragon-native-manifest.json"])
    assert m["status"]=="source_generated"
    assert m["target"]==t
    assert m["runtime_gameplay_mode"]=="original_collectible_chase"
    audit=json.loads(p.files["dragon-hardware-budget.json"])
    assert audit["target"]==t
    assert audit["status"]=="source_budget_checked_only"
    assert "sdk" in p.files["README.md"].lower() or "toolchain" in p.files["README.md"]
    catalog={x["id"]:x for x in target_catalog()}
    assert catalog[t]["status"]=="native_source"
    assert catalog[t]["supported_styles"]==("arcade_score_attack",)

def test_nintendo64_native_joypad_analog_and_real_framebuffer():
    p=generate("nintendo_64")
    src=p.files["src/main.c"]
    for part in ("#include <libdragon.h>","display_init(",
                 "display_get()","display_show(","graphics_fill_screen",
                 "graphics_draw_box(","joypad_init()","joypad_poll()",
                 "joypad_get_inputs(","controller.stick_x",
                 "controller.btn.d_right","score++","level=1+score/5",
                 "hp--","reset()"):
        assert part in src
    assert "N64_INST" in p.files["Makefile"]
    assert "n64.mk" in p.files["Makefile"]
    assert "dragon.z64" in p.files["Makefile"]

def test_nintendo_ds_actual_two_screen_touch_and_bitmap_video():
    p=generate("nintendo_ds")
    source=p.files["src/main.c"]
    for part in ("#include <nds.h>","consoleDemoInit()",
                 "videoSetMode(MODE_5_2D)","vramSetBankA(VRAM_A_MAIN_BG)",
                 "bgInit(3,BgType_Bmp16,BgSize_B16_256x256",
                 "bgGetGfxPtr(bg)","ARGB16(","scanKeys()","touchRead(",
                 "KEY_TOUCH","touch.px","touch.py","KEY_START",
                 "swiWaitForVBlank()","draw_box(x,y",
                 "stage++","life--"):
        assert part in source
    make=p.files["Makefile"]
    assert "libnds" in make and "ndstool" in make
    assert "dragon_ds.nds" not in source
    assert "EBOOT.PBP" not in make

def test_sony_psp_pspsdk_native_lcd_dpad_and_analog_game():
    p=generate("psp")
    c=p.files["src/main.c"]
    for part in ("#include <pspkernel.h>","#include <pspctrl.h>",
                 "#include <pspdisplay.h>","PSP_MODULE_INFO",
                 "PSP_MAIN_THREAD_ATTR","sceCtrlSetSamplingMode",
                 "PSP_CTRL_MODE_ANALOG","sceCtrlPeekBufferPositive",
                 "pad.Lx","pad.Ly","pspDebugScreenInit",
                 "sceDisplayWaitVblankStart","score++","hp--",
                 "PSP_CTRL_CROSS","sceKernelExitGame"):
        assert part in c
    assert "EBOOT.PBP" in p.files["Makefile"]
    assert "PSPSDK" in p.files["Makefile"]

@pytest.mark.parametrize("constructor",[n64_source,ds_source,psp_source])
def test_all_three_console_source_generators_refuse_invalid_seeds(constructor):
    for invalid in (-1,True,0x100000000,3.4,"hacker"):
        with pytest.raises(ValueError):
            constructor(invalid)

def test_late_console_output_does_not_represent_compiled_or_lawfully_ported_game():
    for target in TARGETS:
        p=generate(target)
        assert "Source has NOT been compiled" in p.files["README.md"]
        assert "source_generated" in p.files["dragon-native-manifest.json"]
        assert not any(name.endswith((".z64",".nds",".pbp")) for name in p.files)
        assert p.deferred_mechanics==()
