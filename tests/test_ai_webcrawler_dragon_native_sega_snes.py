"""Native SMS/GG Z80 and SNES 65816 source adapter contracts."""
from __future__ import annotations
from hashlib import sha256
import pytest

from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog


def _project(platform):
    return render_native_project(
        title="Dragon Native Epoch",target_id=platform,
        style="arcade_score_attack",
        candidate_id=sha256(platform.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )

@pytest.mark.parametrize("platform,ext,crt,format_api",[
    ("master_system","sms","crt0_sms.rel","SMS_setSpritePaletteColor"),
    ("game_gear","gg","crt0_sms.rel","GG_setSpritePaletteColor"),
])
def test_sega_z80_native_graphics_controller_and_rom_linking(platform,ext,crt,format_api):
    p=_project(platform)
    assert p.status=="source_generated" and p.output==ext
    assert "src/main.c" in p.files
    source=p.files["src/main.c"]
    for fragment in ("SMS_initSprites()","SMS_addSprite(",
                     "SMS_loadTiles(","SMS_waitForVBlank()",
                     "SMS_getKeysStatus()","PORT_A_KEY_LEFT",
                     "PORT_A_KEY_RIGHT","SMS_copySpritestoSAT()"):
        assert fragment in source
    assert format_api in source
    if platform=="game_gear":
        assert "TARGET_GG" in source
        assert "SMSlib_GG.lib" in p.files["Makefile"]
        assert "-DTARGET_GG" in p.files["Makefile"]
    assert crt in p.files["Makefile"]
    assert "sdcc" in p.files["Makefile"]
    assert "makesms" in p.files["Makefile"]
    assert "dragon."+ext in p.files["Makefile"]
    assert "CMakeLists.txt" not in p.files

def test_snes_65816_homebrew_has_vram_mode_controllers_and_true_lorom_rules():
    p=_project("snes")
    assert p.status=="source_generated" and p.output=="sfc"
    source=p.files["src/main.c"]
    for fragment in ("#include <snes.h>","consoleInitDefaultText",
                     "bgSetGfxPtr(","bgSetMapPtr(","setMode(BG_MODE1",
                     "padsCurrent(0)","KEY_LEFT","KEY_START",
                     "WaitForVBlank();","new_stage()","enemy_cooldown"):
        assert fragment in source
    makefile=p.files["Makefile"]
    assert "PVSNESLIB_HOME" in makefile
    assert "snes_rules" in makefile
    assert "ROMNAME := dragon_snes" in makefile
    assert "ROMTITLE :=" in makefile
    assert "ROMBANKS" not in makefile  # toolkit chooses default
    assert "<html" not in source

def test_new_console_targets_not_claimed_as_device_playtested():
    by_id={t["id"]:t for t in target_catalog()}
    for name in ("snes","master_system","game_gear"):
        target=by_id[name]
        assert target["status"]=="native_source"
        assert target["supported_styles"]==("arcade_score_attack",)
        assert target["toolchain"]
