"""Three incompatible Motorola 68000 homebrew OS games and build custody."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,shutil,subprocess,os
import pytest
from skeleton.ai.webcrawler.dragon_native_m68k_computers import (
    motorola_native_source,ATARI_ST,AMIGA,X68000,
)
from skeleton.ai.webcrawler.dragon_native_projects import (
    render_native_project,EMITTERS,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

M68K=("atari_st","amiga_500","sharp_x68000")
OUTPUT={"atari_st":"tos","amiga_500":"hunk","sharp_x68000":"x"}

@pytest.mark.parametrize("target",M68K)
def test_each_m68k_host_generates_distinct_target_native_game(target):
    project=render_native_project(
        title="Original Dragon Motorola Quest",target_id=target,
        style="arcade_score_attack",
        candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    assert project.status=="source_generated"
    assert project.output==OUTPUT[target]
    assert project.target_id==target
    assert "src/main.c" in project.files
    assert "Makefile" in project.files
    assert "README.port.md" in project.files
    assert "dragon-m68k-contract.json" in project.files
    contract=json.loads(project.files["dragon-m68k-contract.json"])
    assert contract["schema"]=="skeleton.ai.dragon.m68k_native.v1"
    assert contract["target"]==target
    assert contract["compiler_status"]=="source_generated"
    assert contract["emulator_status"]=="unverified"
    assert contract["real_device_status"]=="unverified"
    assert contract["output"]==OUTPUT[target]
    assert project==render_native_project(
        title="Original Dragon Motorola Quest",target_id=target,
        style="arcade_score_attack",
        candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True)
    assert target in EMITTERS
    assert readiness_for(target).source_emitter
    assert not readiness_for(target).compiler_verified
    assert next(x for x in target_catalog() if x["id"]==target)["supported_styles"]==(
        "arcade_score_attack",)
    assert not any(name.endswith((".tos",".x",".adf")) for name in project.files)
    with pytest.raises(ValueError):
        render_native_project(
            title="Original Dragon Motorola Quest",target_id=target,
            style="grand_strategy",candidate_id="f"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_atari_st_uses_actual_tos_bios_68000_and_turn_game():
    code=motorola_native_source("atari_st",7)
    src=code["src/main.c"]
    for token in ("#include <osbind.h>","Cconws(","Crawcin()",
                  "Bconout(2,c)","health--","shield=4","score++",
                  "level=1+score/4","Cconws(\"\\033E"):
        assert token in src
    assert "m68k-atari-mint-gcc" in code["Makefile"]
    assert "-m68000" in code["Makefile"]
    assert "dragon.tos" in code["Makefile"]
    assert "SDL" not in src

def test_amiga_500_has_real_intuition_13_window_and_rastport():
    code=motorola_native_source("amiga_500",7)
    src=code["src/main.c"]
    for token in ("#include <intuition/intuition.h>",
                  "#include <graphics/rastport.h>",
                  "OpenLibrary(\"intuition.library\",0)",
                  "OpenLibrary(\"graphics.library\",0)",
                  "OpenWindow(&window_spec)",
                  "IDCMP_VANILLAKEY","IDCMP_CLOSEWINDOW",
                  "WaitPort(win->UserPort)","GetMsg(win->UserPort)",
                  "ReplyMsg((struct Message*)m)","RectFill(",
                  "SetAPen(","Text(rp,","CloseWindow(win)",
                  "hp--","shield=4","score++"):
        assert token in src
    assert "vc" in code["Makefile"] and "+kick13" in code["Makefile"]
    assert "build/dragon" in code["Makefile"]
    assert "SDL" not in src

def test_sharp_uses_human68k_native_dos_and_elf_to_x_file():
    code=motorola_native_source("sharp_x68000",7)
    src=code["src/main.c"]
    for token in ("#include <sys/dos.h>","_dos_getchar()",
                  "_dos_putchar(ch)","score++","hp--","shield=4"):
        assert token in src
    assert "m68k-human68k-gcc" in code["Makefile"]
    assert "elf2x68k" in code["Makefile"]
    assert "dragon.elf" in code["Makefile"]
    assert "dragon.x" in code["Makefile"]
    assert "SDL" not in src

def test_three_native_games_do_not_share_fake_graphics_or_build_format():
    source=[motorola_native_source(t,881) for t in M68K]
    sha={sha256(x["src/main.c"].encode()).hexdigest() for x in source}
    assert len(sha)==3
    for t in M68K:
        assert motorola_native_source(t,41)!=motorola_native_source(t,42)
        assert motorola_native_source(t,41)==motorola_native_source(t,41)
        for invalid in (True,-1,2**32,10.5,"code"):
            with pytest.raises(ValueError):
                motorola_native_source(t,invalid)
    with pytest.raises(ValueError):
        motorola_native_source("licensed_ps5",50)

@pytest.mark.parametrize("target,compiler",[
    ("atari_st","m68k-atari-mint-gcc"),
    ("amiga_500","vc"),
    ("sharp_x68000","m68k-human68k-gcc"),
])
def test_native_68000_compile_only_with_actual_sdk(tmp_path,target,compiler):
    files=motorola_native_source(target,2026)
    required=[compiler,"make"]
    if target=="sharp_x68000":
        required.append("elf2x68k")
    if not all(shutil.which(c) for c in required):
        pytest.skip("actual OS-specific m68k toolchain missing: "+compiler)
    # vbcc only runs with kick13 config and installed Amiga target NDK.
    if target=="amiga_500" and not os.environ.get("VBCC"):
        pytest.skip("vbcc Kickstart 1.3 config/SDK unavailable")
    for name,data in files.items():
        path=tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(data,encoding="utf-8")
    build=subprocess.run(["make","-C",str(tmp_path)],timeout=120,
            capture_output=True,text=True)
    assert build.returncode==0,(build.stdout,build.stderr)
    file={"atari_st":"build/dragon.tos","amiga_500":"build/dragon",
          "sharp_x68000":"build/dragon.x"}[target]
    binary=tmp_path/file
    assert binary.is_file() and binary.stat().st_size>256
