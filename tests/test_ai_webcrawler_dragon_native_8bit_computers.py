"""Five truly native retro-computer game sources: ABI, input, graphics, SDK builds."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json,os,pytest,shutil,subprocess
from skeleton.ai.webcrawler.dragon_native_8bit_computers import (
    computer_source,PLATFORMS,
)
from skeleton.ai.webcrawler.dragon_native_projects import (
    render_native_project,EMITTERS,
)
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

TARGETS={
    "commodore_vic20":("cc65","vic20","prg"),
    "commodore_128":("cc65","c128","prg"),
    "atari_400_800":("cc65","atari","xex"),
    "msx1":("z88dk","msx","bin"),
    "amstrad_cpc":("z88dk","cpc","bin"),
}

def _game(target:str):
    return render_native_project(
        title="Original Dragon Eight Bit",
        target_id=target,style="arcade_score_attack",
        candidate_id=sha256(("retro"+target).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )

@pytest.mark.parametrize("target,tool_tuple",TARGETS.items())
def test_emits_machine_specific_source_and_never_claims_verified_binaries(target,tool_tuple):
    p=_game(target)
    compiler,cpu,extension=tool_tuple
    assert p.target_id==target and p.status=="source_generated"
    assert p.output==extension
    assert ("src/main.s" if target=="commodore_vic20" else "src/main.c") in p.files
    assert "Makefile" in p.files
    assert "README.port.md" in p.files
    assert "CMakeLists.txt" not in p.files
    assert "native" in p.files["README.port.md"].lower()
    assert p==_game(target)
    assert not any(name.endswith((".rom",".prg",".xex",".bin",".dsk"))
                   for name in p.files)
    assert target in EMITTERS
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["target"]==target
    assert manifest["status"]=="source_generated"
    assert manifest["runtime_gameplay_mode"]=="original_collectible_chase"
    readiness=readiness_for(target)
    assert readiness.claimed_stage=="native_source_generated"
    assert not readiness.compiler_verified
    assert not readiness.controller_replay_verified
    row=next(t for t in target_catalog() if t["id"]==target)
    assert row["status"]=="native_source"
    assert row["supported_styles"]==("arcade_score_attack",)
    with pytest.raises(ValueError):
        render_native_project(
            title="Original Dragon Eight Bit",
            target_id=target,style="fighting_game",
            candidate_id="f"*64,mechanics=(Mechanic.MOVEMENT,),authorized=True)

@pytest.mark.parametrize("target",TARGETS)
def test_source_has_real_gameplay_and_correct_machine_io(target):
    native=computer_source(target,31)
    if target=="commodore_vic20":
        asm=native["src/main.s"]
        for term in ("KERNAL_GETIN = $FFE4","Screen = $1E00",
                     "VIC_BORDER = $900F","VIC_VOLUME = $900E",
                     "Update:","DrawAt:","inc Score","dec Lives",
                     "GameLoop:","JSR","KERNAL_GETIN"):
            assert term.lower() in asm.lower()
        assert "$(CA65)" in native["Makefile"] and "$(LD65)" in native["Makefile"]
        assert "vic20.cfg" in native
        assert 'start=$1001' in native["vic20.cfg"]
        assert "size=$0BFF" in native["vic20.cfg"]
        return
    source=native["src/main.c"]
    expected=TARGETS[target]
    for phrase in (
        "#include <conio.h>","next_rng()","static void advance(char key)",
        "machine_init()","machine_pickup()","hero_x",
        "gem_x","foe_x","if(score%5==0&&hp<5)hp++",
        "score++","hp--","cgetc()" if target not in ("msx1","amstrad_cpc")
        else "getch()",
    ):
        assert phrase in source
    assert "SDL_" not in source
    assert "http://" not in source
    if expected[0]=="cc65":
        assert "$(CL65) -t "+expected[1] in native["Makefile"]
        assert "#include <peekpoke.h>" in source
    else:
        assert "$(ZCC) +"+expected[1] in native["Makefile"]
        assert "-clib=ansi" in native["Makefile"]
    if target=="commodore_vic20":
        assert "POKE(0x900F" in source and "POKE(0x900E" in source
        assert "#define FIELD_W 20" in source
    if target=="commodore_128":
        assert "POKE(0xD020" in source and "POKE(0xD418" in source
    if target=="atari_400_800":
        assert "POKE(0x02C8" in source and "POKE(0xD201" in source
    if target=="msx1":
        assert "textcolor(15)" in source
    if target=="amstrad_cpc":
        assert "textcolor(3)" in source

@pytest.mark.parametrize("target",TARGETS)
def test_bounded_source_seed_and_deterministic_cross_compilation_input(target):
    assert computer_source(target,7)==computer_source(target,7)
    assert computer_source(target,7)!=computer_source(target,9)
    for bad in (-1,2**32,True,3.0,"3",None):
        with pytest.raises(ValueError):
            computer_source(target,bad)

@pytest.mark.parametrize("target",TARGETS)
def test_real_eight_bit_cross_compiler_when_tool_installed(tmp_path,target):
    compiler=TARGETS[target][0]
    tool=("ca65" if target=="commodore_vic20" else
          "cl65" if compiler=="cc65" else "zcc")
    if not shutil.which(tool) or not shutil.which("make"):
        pytest.skip("real 8-bit cross compiler is not installed: "+tool)
    files=computer_source(target,123)
    for name,body in files.items():
        out=tmp_path/name
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(body,encoding="utf-8")
    run=subprocess.run(["make","-C",str(tmp_path),"all"],
        capture_output=True,text=True,timeout=100)
    assert run.returncode==0,(run.stdout,run.stderr)
    wanted=tmp_path/"build"/("dragon."+TARGETS[target][2])
    assert wanted.exists()
    assert wanted.stat().st_size>0
    assert wanted.stat().st_size<1_000_000
    if target=="commodore_vic20":
        # This is a genuine BASIC loadable PRG for a 5K unexpanded VIC.
        # Load address $1001 precedes the BASIC SYS 4109 launcher.
        rom=wanted.read_bytes()
        assert rom[:2]==bytes([0x01,0x10])
        assert b"4109" in rom[:20]
        assert len(rom)<3072
