"""Four original machine-native games; exact-source and compiler evidence gates.

Source generation is not equivalent to binary/device verification.
Tests fail if an unsupported platform is given a fake executable or if an
unrelated SDK target/keyboard layout is copied into the machine source.
"""
from __future__ import annotations
from hashlib import sha256
import json,shutil,subprocess
import pytest
from skeleton.ai.webcrawler.dragon_native_atari_z80_new import native_machine_source
from skeleton.ai.webcrawler.dragon_native_projects import (
    EMITTERS,render_native_project,
)
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import (
    readiness_for,coverage_report,
)
from skeleton.ai.webcrawler.dragon_platform_expansion import SUPPLEMENTAL_TARGETS

NEW={
    "atari_5200":"bin",
    "colecovision":"rom",
    "zx81":"p",
    "msx2":"com",
}

def _render(target:str):
    return render_native_project(
        title="Dragon Original Cross-Era",target_id=target,
        style="arcade_score_attack",
        candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )

def test_unique_platform_id_count_170_and_76_original_native_source_targets():
    assert len(SUPPLEMENTAL_TARGETS)==123
    assert len(EMITTERS)==76
    assert coverage_report()["catalog_count"]==169
    assert coverage_report()["missing_native_source_count"]==93
    assert coverage_report()["source_coverage_fraction"]==round(76/170,6)
    assert {key for key in NEW if not readiness_for(key).source_emitter}==set()

@pytest.mark.parametrize("target,extension",list(NEW.items()))
def test_native_5200_coleco_zx81_msx2_project_claims_only_original_source(
    target,extension,
):
    one=_render(target)
    assert one.target_id==target
    assert one.status=="source_generated"
    assert one.output==extension
    assert one.files["src/main.c"]
    assert one.files["Makefile"]
    assert one.files["README.port.md"]
    assert "CMakeLists.txt" not in one.files
    assert one.files==_render(target).files
    assert one.digest==_render(target).digest
    assert not any(n.endswith((".bin",".rom",".p",".com"))
                   for n in one.files)
    m=json.loads(one.files["dragon-native-manifest.json"])
    assert m["target"]==target
    assert m["output_extension"]==extension
    assert m["status"]=="source_generated"
    assert m["runtime_gameplay_mode"]=="original_collectible_chase"
    a=readiness_for(target)
    assert a.source_emitter and not a.compiler_verified
    assert not a.physical_hardware_verified
    assert not a.distribution_approved
    row=next(x for x in target_catalog() if x["id"]==target)
    assert row["status"]=="native_source"
    assert row["supported_styles"]==("arcade_score_attack",)
    with pytest.raises(ValueError):
        render_native_project(
            title="Dragon Original Cross-Era",target_id=target,
            style="grand_strategy",candidate_id="f"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True,
        )

def test_atari_5200_statically_linked_real_analog_controller_and_antic_console():
    game=native_machine_source("atari_5200",0xCB65)
    c=game["src/main.c"]
    for required in (
        "#include <atari5200.h>", "#include <joystick.h>",
        "joy_install(joy_static_stddrv)", "joy_read(0)",
        "JOY_LEFT_MASK", "JOY_RIGHT_MASK", "JOY_UP_MASK",
        "JOY_DOWN_MASK", "JOY_BTN_1_MASK",
        "waitvsync()", "OS.color0", "OS.color1", "OS.color2",
        "gotoxy(px,py)", "life--", "score++", "level=1+score/4",
    ):
        assert required in c
    assert "-t atari5200" in game["Makefile"]
    assert "build/dragon.bin" in game["Makefile"]
    assert "PC DOS" not in game["README.port.md"]

def test_colecovision_uses_real_vdp_crt_joystick_not_pc_or_keypad_keyboard():
    game=native_machine_source("colecovision",0x42)
    c=game["src/main.c"]
    assert "#include <games.h>" in c
    assert "joystick(1)" in c
    assert "gotoxy(gx,gy)" in c and "putch('*')" in c
    assert "clrscr()" in c and "frame%" in c
    assert "score++" in c and "hp--" in c
    assert "-create-app -bn build/dragon" in game["Makefile"]
    assert "+coleco" in game["Makefile"]
    assert "build/dragon.rom" in game["Makefile"]
    assert not any(x in c for x in ("SDL_","WinMain","bios_call"))

def test_zx81_requires_native_16k_text_machine_and_real_keyboard():
    game=native_machine_source("zx81",101)
    c=game["src/main.c"]
    assert "16K RAM" in c
    assert "kbhit()" in c and "getch()" in c
    assert "read_zx81_keys()" in c
    assert "joystick(1)" not in c
    assert "getch()" in c and "flags|=16" in c
    assert "+zx81" in game["Makefile"]
    assert "build/dragon.p" in game["Makefile"]
    assert "no fictional analog joystick" in game["README.port.md"]

def test_msx2_native_bios_controller_and_truthful_dos_executable():
    game=native_machine_source("msx2",102)
    c=game["src/main.c"]
    assert "#include <msx.h>" in c
    assert "msx_screen(0)" in c
    assert "msx_get_stick(1)" in c
    assert "msx_get_trigger(1)" in c
    for v in range(1,9):
        assert f"v=={v}" in c
    assert "textcolor(10)" in c
    assert "score++" in c and "level=1+score/4" in c
    assert "-subtype=msxdos" in game["Makefile"]
    assert "build/dragon.com" in game["Makefile"]
    assert "MSX-DOS" in game["README.port.md"] or "BIOS" in game["README.port.md"]

@pytest.mark.parametrize("target",list(NEW))
def test_original_machine_outputs_are_seed_stable_and_finite(target):
    one=native_machine_source(target,2026)
    assert one==native_machine_source(target,2026)
    assert one!=native_machine_source(target,2027)
    assert 100 < len(one["src/main.c"]) < 120000
    assert "__SEED__" not in one["src/main.c"]
    assert all("/../" not in name and not name.startswith("/")
               for name in one)
    for invalid in (-1,2**32,True,3.3,"../../etc/passwd"):
        with pytest.raises(ValueError):
            native_machine_source(target,invalid)
    with pytest.raises(ValueError):
        native_machine_source("not_a_platform",0)

def test_atari5200_compiles_real_cc65_cartridge_bytes_if_available(tmp_path):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("cc65 target compiler not installed")
    files=native_machine_source("atari_5200",11)
    for name,body in files.items():
        p=tmp_path/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(body,encoding="utf-8")
    result=subprocess.run(["make","-C",str(tmp_path)],timeout=70,
                          capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    rom=(tmp_path/"build"/"dragon.bin")
    assert rom.is_file()
    assert 1000<=rom.stat().st_size<65536

@pytest.mark.parametrize("target,output",[
    ("colecovision","dragon.rom"),
    ("zx81","dragon.p"),
    ("msx2","dragon.com"),
])
def test_z80_cross_compilation_if_z88dk_toolchain_present(tmp_path,target,output):
    if not shutil.which("zcc") or not shutil.which("make"):
        pytest.skip("exact z88dk cross compiler unavailable")
    files=native_machine_source(target,9)
    for name,body in files.items():
        p=tmp_path/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(body,encoding="utf-8")
    done=subprocess.run(["make","-C",str(tmp_path)],timeout=110,
                        capture_output=True,text=True)
    assert done.returncode==0,(done.stdout,done.stderr)
    generated=(tmp_path/"build"/output)
    assert generated.is_file()
    assert 100<=generated.stat().st_size<131072
