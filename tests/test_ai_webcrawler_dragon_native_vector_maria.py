"""Native 6809 Vectrex vectors and 6502/MARIA Atari 7800 source + PNG build."""
from __future__ import annotations
import json,os,sys,struct,zlib,subprocess,shutil
from hashlib import sha256
from pathlib import Path
import pytest
from skeleton.ai.webcrawler.dragon_native_vector_maria import native_vector_maria_source
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project,EMITTERS
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for,coverage_report
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

TARGETS=(("vectrex","bin"),("atari_7800","a78"))
def make(target:str):
    return render_native_project(
        title="Original Dragon Hardware Quest",target_id=target,
        style="arcade_score_attack",candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)

@pytest.mark.parametrize("target,extension",TARGETS)
def test_original_source_project_not_renamed_pc_game(target,extension):
    game=make(target)
    assert game.status=="source_generated"
    assert game.output==extension and game.target_id==target
    assert game.files==make(target).files and game.digest==make(target).digest
    assert game.files["Makefile"] and game.files["README.port.md"]
    assert "CMakeLists.txt" not in game.files
    assert not any(name.endswith((".a78",".bin",".exe")) for name in game.files)
    manifest=json.loads(game.files["dragon-native-manifest.json"])
    assert manifest["target"]==target
    assert manifest["output_extension"]==extension
    assert manifest["status"]=="source_generated"
    assert manifest["runtime_gameplay_mode"]=="original_collectible_chase"
    assert not readiness_for(target).compiler_verified
    assert not readiness_for(target).physical_hardware_verified
    assert target in EMITTERS
    row=next(x for x in target_catalog() if x["id"]==target)
    assert row["status"]=="native_source"
    assert row["supported_styles"]==("arcade_score_attack",)
    assert coverage_report()["native_source_count"]==len(EMITTERS)
    assert len(EMITTERS)>=87
    with pytest.raises(ValueError):
        render_native_project(
            title="Original Dragon Hardware Quest",target_id=target,
            style="grand_strategy",candidate_id="a"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_vectrex_motorola_6809_real_vector_bios_controller_and_psg():
    c=native_vector_maria_source("vectrex",2026)["src/main.c"]
    for token in (
        "#include <vectrex/bios.h>","wait_recal()","intensity_a(",
        "reset0ref()","moveto_d(","draw_vl_a(","draw_line_d(",
        "controller_enable_1_x()","controller_enable_1_y()",
        "controller_check_joysticks()","controller_check_buttons()",
        "controller_joystick_1_left()","controller_joystick_1_right()",
        "controller_button_1_1_pressed()","sound_byte(",
        "update_audio()","hp--","score++","stage=1+score/5",
        "if(!hp)","guard=32",
    ):
        assert token in c
    assert "SDL_" not in c and "WinMain" not in c
    makefile=native_vector_maria_source("vectrex",2026)["Makefile"]
    assert "--vectrex" in makefile and "CMOC" in makefile
    assert "-o $@ $<" in makefile

def test_atari_7800_maria_sprite_game_and_original_standard_library_art(tmp_path):
    game=native_vector_maria_source("atari_7800",2060)
    bas=game["src/main.bas"]
    for token in ("displaymode 160A","set zoneheight 16",
       "incgraphic images/dragon.png 160A",
       "incgraphic images/crystal.png 160A",
       "incgraphic images/foe.png 160A",
       "plotsprite dragon 0","plotsprite crystal 1",
       "plotsprite foe 2","drawscreen","joy0left","joy0up","joy0fire0",
       "boxcollision(","score" if False else "points = points + 1",
       "hp = hp - 1","guardFrames = 40","goto _initGame"):
        assert token in bas
    build=game["Makefile"]
    assert "7800bas" in build and "build/dragon.a78" in build
    assert "tools/create_assets.py" in game
    for name,data in game.items():
        p=tmp_path/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(data)
    script=tmp_path/"tools/create_assets.py"
    subprocess.run([sys.executable,"-I",str(script)],cwd=tmp_path,
                   timeout=15,check=True,capture_output=True,text=True)
    collected=[]
    for name in ("dragon","crystal","foe"):
        raw=(tmp_path/"images"/(name+".png")).read_bytes()
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(raw)<1024
        assert raw[12:16]==b"IHDR"
        assert struct.unpack(">II",raw[16:24])==(8,16)
        assert raw[24]==8 and raw[25]==3 # indexed 4-colour PNG
        pos=8
        compressed=b""
        while pos<len(raw):
            size=int.from_bytes(raw[pos:pos+4],"big")
            typ=raw[pos+4:pos+8]
            blob=raw[pos+8:pos+8+size]
            crc=int.from_bytes(raw[pos+8+size:pos+12+size],"big")
            assert zlib.crc32(typ+blob)&0xffffffff==crc
            if typ==b"IDAT":compressed+=blob
            pos+=12+size
        pixels=zlib.decompress(compressed)
        assert len(pixels)==16*9
        assert all(pixels[i]==0 for i in range(0,144,9))
        assert max(pixels)<=3
        collected.append(sha256(raw).hexdigest())
    assert len(set(collected))==3
    again=subprocess.run([sys.executable,"-I",str(script)],cwd=tmp_path,
                         timeout=15,check=True,capture_output=True,text=True)
    assert again.returncode==0
    for name,digest in zip(("dragon","crystal","foe"),collected):
        assert sha256((tmp_path/"images"/(name+".png")).read_bytes()).hexdigest()==digest

@pytest.mark.parametrize("target",("vectrex","atari_7800"))
def test_strict_u32_seed_and_distinct_original_assets(target):
    assert native_vector_maria_source(target,10)!=native_vector_maria_source(target,11)
    assert native_vector_maria_source(target,10)==native_vector_maria_source(target,10)
    for bad in (-1,2**32,True,2.1,"remote"):
        with pytest.raises(ValueError):
            native_vector_maria_source(target,bad)
    with pytest.raises(ValueError):
        native_vector_maria_source("ps5",10)

@pytest.mark.parametrize("target,tool",(
    ("vectrex","cmoc"),("atari_7800","7800bas"),
))
def test_actual_native_compiler_only_if_toolchain_installed(tmp_path,target,tool):
    if not shutil.which(tool) or not shutil.which("make"):
        pytest.skip(tool+" and appropriate target SDK are required")
    if target=="vectrex" and not os.environ.get("VECTREC"):
        pytest.skip("explicit VectreC stdlib path required")
    source=native_vector_maria_source(target,42)
    for name,body in source.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(body)
    env={**os.environ}
    if target=="vectrex":env["VECTREC"]=os.environ["VECTREC"]
    process=subprocess.run(["make","-C",str(tmp_path),"all"],timeout=120,
                           capture_output=True,text=True,env=env)
    assert process.returncode==0,(process.stdout,process.stderr)
    expected=tmp_path/"build"/("dragon.bin" if target=="vectrex" else "dragon.a78")
    assert expected.stat().st_size>0
