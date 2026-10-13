"""Intellivision 1979 genuine STIC MOB and AY PSG homebrew source."""
from __future__ import annotations
import pytest,json,shutil,subprocess
from hashlib import sha256
from pathlib import Path
from skeleton.ai.webcrawler.dragon_native_intellivision import intellivision_source
from skeleton.ai.webcrawler.dragon_native_projects import EMITTERS,render_native_project
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for,coverage_report
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

def make():
    return render_native_project(title="Original Dragon CP1610 Quest",
       target_id="intellivision",style="arcade_score_attack",
       candidate_id=sha256(b"Original Dragon CP1610 Quest").hexdigest(),
       mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)

def test_intellivision_original_hardware_source_and_readiness():
    p=make()
    assert p==make() and p.status=="source_generated"
    assert p.target_id=="intellivision" and p.output=="bin"
    assert "src/main.bas" in p.files and "Makefile" in p.files
    assert "README.port.md" in p.files
    assert "CMakeLists.txt" not in p.files
    assert not any(k.endswith(".bin") for k in p.files)
    m=json.loads(p.files["dragon-native-manifest.json"])
    assert m["status"]=="source_generated"
    assert m["target"]=="intellivision"
    assert m["output_extension"]=="bin"
    assert m["runtime_gameplay_mode"]=="original_collectible_chase"
    assert "intellivision" in EMITTERS
    assert coverage_report()["native_source_count"]==len(EMITTERS)
    assert not readiness_for("intellivision").compiler_verified
    assert not readiness_for("intellivision").controller_replay_verified
    row=next(x for x in target_catalog() if x["id"]=="intellivision")
    assert row["status"]=="native_source"
    assert row["supported_styles"]==("arcade_score_attack",)
    with pytest.raises(ValueError):
        render_native_project(title="Original Dragon CP1610 Quest",
          target_id="intellivision",style="grand_strategy",
          candidate_id="a"*64,mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_real_intellivision_stic_mob_gram_input_sound_and_original_art():
    p=intellivision_source(42)
    s=p["src/main.bas"]
    for token in ("OPTION EXPLICIT","DEFINE 0,1,dragonArt",
       "DEFINE 1,1,gemArt","DEFINE 2,1,enemyArt",
       "SPRITE 0,playerX+$200","SPRITE 1,gemX+$200",
       "SPRITE 2,enemyX+$200","CONT1.LEFT","CONT1.RIGHT",
       "CONT1.UP","CONT1.DOWN","CONT1.B0",
       "SOUND 0,78,12","SOUND 0,146,13",
       "BITMAP \"..XXXX..\"","IF energy=0 THEN GOTO DEAD",
       "score=score+1","guard=28","GOSUB HUNT","WAIT"):
       assert token in s
    assert s.count("BITMAP \"")==24
    assert "SDL_" not in s and "WinMain" not in s
    m=p["Makefile"]
    assert "$(INTYBASIC)" in m and "$(AS1600)" in m
    assert "build/dragon.bin" in m
    assert "src/main.bas" in m and "build/dragon.asm" in m
    assert "cartridge" in p["README.port.md"]
    assert "EXEC/GROM" in p["README.port.md"]

def test_seed_validation_and_replay_identity():
    assert intellivision_source(5)==intellivision_source(5)
    assert intellivision_source(5)!=intellivision_source(6)
    for bad in (-1,2**32,True,2.4,"5",None):
        with pytest.raises(ValueError):
            intellivision_source(bad)

def test_inty_basic_and_as1600_compile_when_available(tmp_path):
    if not (shutil.which("intybasic") and shutil.which("as1600") and
            shutil.which("make")):
        pytest.skip("separately installed genuine CP1610 IntyBASIC/as1600 required")
    p=intellivision_source(2026)
    for rel,body in p.items():
        dest=tmp_path/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(body)
    result=subprocess.run(["make","-C",str(tmp_path)],timeout=120,
                          capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert (tmp_path/"build/dragon.bin").stat().st_size>0
