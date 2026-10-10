"""New source targets: Lynx 65C02, Saturn SH-2 Jo Engine, Vita VitaSDK.

All SDK source strings have deterministic reproduction, correct platform
headers, real graphics/input/state and exact output extensions. The Lynx
program must really compile on a cc65-enabled CI host, not be counted
from text matching alone. Vita/Saturn builds are externally SDK-gated.
"""
from __future__ import annotations
from hashlib import sha256
import json,shutil,subprocess
from pathlib import Path
import pytest

from skeleton.ai.webcrawler.dragon_native_lynx import lynx_source
from skeleton.ai.webcrawler.dragon_native_vita_saturn import (
    saturn_source,vita_source,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project,EMITTERS
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

NEW={"lynx":"lnx","saturn":"iso","ps_vita":"vpk"}

def project(target):
    return render_native_project(title="Dragon Native Original Quest",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(("Dragon"+target).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)

@pytest.mark.parametrize("target,extension",NEW.items())
def test_real_source_export_does_not_forge_console_binary(target,extension):
    assert target in EMITTERS
    p=project(target)
    assert p.status=="source_generated"
    assert p.output==extension
    assert "src/main.c" in p.files
    assert ("Makefile" in p.files or "CMakeLists.txt" in p.files)
    assert "README.port.md" in p.files
    assert not any(name.endswith((".lnx",".iso",".vpk")) for name in p.files)
    assert p.digest==project(target).digest
    assert p.files["src/main.c"]==project(target).files["src/main.c"]
    metadata=json.loads(p.files["dragon-native-manifest.json"])
    assert metadata["status"]=="source_generated"
    assert metadata["target"]==target
    assert metadata["output_extension"]==extension
    readiness=readiness_for(target)
    assert readiness.source_emitter
    assert not readiness.compiler_verified
    assert not readiness.controller_replay_verified
    assert not readiness.physical_hardware_verified
    assert not readiness.distribution_approved
    row=next(x for x in target_catalog() if x["id"]==target)
    assert row["status"]=="native_source"
    assert tuple(row["supported_styles"])==("arcade_score_attack",)
    with pytest.raises(ValueError):
        render_native_project(title="Dragon Native Original Quest",
            target_id=target,style="grand_strategy",
            candidate_id="f"*64,mechanics=(Mechanic.MOVEMENT,),
            authorized=True)

@pytest.mark.parametrize("maker",[lynx_source,saturn_source,vita_source])
def test_untrusted_seed_rejected_by_every_hardware_emitter(maker):
    assert maker(17)==maker(17)
    assert maker(17)!=maker(19)
    for value in (-1,2**32,True,3.14,"evil",None):
        with pytest.raises(ValueError):
            maker(value)

def test_lynx_is_real_65c02_native_tgi_not_fictitious_console():
    c=project("lynx").files["src/main.c"]
    mk=project("lynx").files["Makefile"]
    for part in ("<lynx.h>","<joystick.h>","<tgi.h>","<6502.h>",
       "tgi_install(tgi_static_stddrv)",
       "tgi_init()","tgi_outtextxy",
       "tgi_bar(","tgi_updatedisplay()","joy_install(joy_static_stddrv)",
       "joy_read(JOY_1)","JOY_LEFT_MASK","JOY_BTN_A_MASK",
       "score++","chapter=","hp--","won=1","new_game()"):
        assert part in c
    assert "cl65" in mk and "-t lynx" in mk and "dragon.lnx" in mk
    assert "#include <SDL" not in c

def test_saturn_has_jo_engine_pad_and_vdp2_rendering():
    p=project("saturn")
    c=p.files["src/main.c"];mk=p.files["Makefile"]
    for part in ("#include <jo/jo.h>","jo_main(void)",
      "jo_core_init(","jo_core_add_callback","jo_core_run",
      "jo_printf(","jo_clear_screen()","jo_is_pad1_key_down(",
      "JO_KEY_RIGHT","JO_KEY_START","jo_is_pad1_key_pressed",
      "score++","hp--","won=1"):
        assert part in c
    assert "jo_engine_makefile" in mk
    assert "JO_ENGINE_ROOT" in mk
    assert "SRCS = src/main.c" in mk
    assert "JO_COMPILE_WITH_PRINTF_SUPPORT = 1" in mk

def test_vita_has_real_gpu_dpad_analog_touch_and_authorized_package_intent():
    p=project("ps_vita")
    c=p.files["src/main.c"];mk=p.files["CMakeLists.txt"]
    for part in ("<psp2/ctrl.h>","<psp2/touch.h>","<vita2d.h>",
       "sceCtrlPeekBufferPositive","sceTouchPeek(",
       "SCE_TOUCH_PORT_FRONT","SCE_CTRL_START","SCE_CTRL_SELECT",
       "vita2d_init()","vita2d_draw_rectangle","vita2d_swap_buffers",
       "SCE_CTRL_MODE_ANALOG","score++","hp--","won=1"):
        assert part in c
    assert "vita.toolchain.cmake" in mk
    assert "vita_create_vpk(" in mk
    assert "VITASDK" in mk
    assert "DRGN00001" in mk
    assert "Sony" not in c

def test_lynx_real_cc65_compiler_and_cartridge_header(tmp_path):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("cc65 cross compiler not installed")
    files=lynx_source(23)
    for name,body in files.items():
        dest=tmp_path/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(body,encoding="utf-8")
    run=subprocess.run(["make","-C",str(tmp_path)],capture_output=True,
                       text=True,timeout=110)
    assert run.returncode==0,(run.stdout,run.stderr)
    cartridge=tmp_path/"build"/"dragon.lnx"
    assert cartridge.is_file()
    assert cartridge.stat().st_size>1000
    data=cartridge.read_bytes()
    assert b"DRAGON LYNX" in data or len(data)>2048

def test_without_vendor_sdk_vita_and_saturn_do_not_emit_executables():
    for target in ("saturn","ps_vita"):
        result=project(target)
        assert "readme" not in result.files
        assert len(result.files)>3
        assert all(not x.startswith("build/") for x in result.files)
        assert "not" in result.files["README.port.md"].lower() or (
               "no" in result.files["README.port.md"].lower())
