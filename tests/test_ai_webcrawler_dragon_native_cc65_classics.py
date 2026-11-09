"""Four original 6502 native game backends and actual cc65 builds."""
from __future__ import annotations
from hashlib import sha256
import json,shutil,subprocess
import pytest
from skeleton.ai.webcrawler.dragon_native_cc65_classics import (
    classic_cc65_source,CLASSICS,
)
from skeleton.ai.webcrawler.dragon_native_projects import (
    render_native_project,EMITTERS,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog
from skeleton.ai.webcrawler.dragon_hardware_budget import budget_for
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

TARGETS=tuple(CLASSICS)

@pytest.mark.parametrize("target",TARGETS)
def test_native_6502_source_is_original_game_and_not_fake_disk_image(target):
    p=render_native_project(
        title="Dragon Original 6502 Maze",target_id=target,
        style="arcade_score_attack",candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
    )
    assert p.target_id==target and p.status=="source_generated"
    assert p.output==CLASSICS[target].output
    assert "src/main.c" in p.files and "Makefile" in p.files
    assert "README.port.md" in p.files
    assert "CMakeLists.txt" not in p.files
    assert "SDL" not in p.files["src/main.c"]
    assert not any(k.endswith((".ssd",".dsk",".prg",".bin")) for k in p.files)
    assert "score+=10" in p.files["src/main.c"]
    assert "enemy_turn(void)" in p.files["src/main.c"]
    assert "keypress(char key)" in p.files["src/main.c"]
    assert "passable(unsigned char col" in p.files["src/main.c"]
    assert "clrscr()" in p.files["src/main.c"]
    assert "cgetc()" in p.files["src/main.c"]
    assert f"CC65_TARGET := {CLASSICS[target].cc65}" in p.files["Makefile"]
    assert "target-native" in p.files["README.port.md"]
    assert p==render_native_project(
        title="Dragon Original 6502 Maze",target_id=target,
        style="arcade_score_attack",candidate_id=sha256(target.encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["target"]==target
    assert manifest["status"]=="source_generated"
    assert manifest["runtime_gameplay_mode"]=="original_collectible_chase"
    hardware=json.loads(p.files["dragon-hardware-budget.json"])
    assert hardware["target"]==target
    assert budget_for(target).working_ram_bytes>5000
    assert readiness_for(target).source_emitter
    assert not readiness_for(target).compiler_verified
    assert target in EMITTERS
    row=next(t for t in target_catalog() if t["id"]==target)
    assert row["status"]=="native_source"
    assert row["supported_styles"]==("arcade_score_attack",)

@pytest.mark.parametrize("target",TARGETS)
def test_native_classic_refuses_unsupported_modes_and_malformed_seeds(target):
    for bad in (True,-1,2**32,3.14,"hello",None):
        with pytest.raises(ValueError):
            classic_cc65_source(target,bad)
    with pytest.raises(ValueError):
        render_native_project(
            title="Dragon Original 6502 Maze",target_id=target,
            style="grand_strategy",candidate_id="b"*64,
            mechanics=(Mechanic.MOVEMENT,),authorized=True)

def test_monochrome_pet_has_no_color_dependency():
    p=classic_cc65_source("commodore_pet",3)
    assert "#define COLOUR 0" in p["src/main.c"]
    assert "#if COLOUR" in p["src/main.c"]
    assert "textcolor" in p["src/main.c"]
    for target in TARGETS[1:]:
        assert "#define COLOUR 1" in classic_cc65_source(target,3)["src/main.c"]

@pytest.mark.parametrize("target",TARGETS)
def test_generated_home_computer_program_compiles_with_real_cc65(
    tmp_path,target,
):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("native cc65 compiler unavailable; source is not compiled")
    root=tmp_path/target
    files=classic_cc65_source(target,0x12345678)
    for relative,body in files.items():
        file=root/relative
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(body,encoding="utf-8")
    if target=="bbc_micro":
        # Ubuntu's cc65 distribution exposes -t bbc, but does not ship
        # bbc.lib. Compile native 6502 object, then skip link verification
        # unless the actual target runtime archive is present.
        from pathlib import Path
        runtime=subprocess.run(["cl65","--print-target-path"],
                               capture_output=True,text=True,timeout=10)
        candidates=[]
        if runtime.returncode==0 and runtime.stdout.strip():
            base=Path(runtime.stdout.strip()).resolve()
            candidates.extend([base.parent/"lib"/"bbc.lib",
                               base/"lib"/"bbc.lib"])
        import os
        for variable in ("CC65_HOME","LD65_LIB"):
            if os.environ.get(variable):
                base=Path(os.environ[variable])
                candidates.extend([base/"bbc.lib",base/"lib"/"bbc.lib"])
        if not any(candidate.is_file() for candidate in candidates):
            object_file=root/"build"/"main.o"
            object_file.parent.mkdir(parents=True,exist_ok=True)
            check=subprocess.run(["cl65","-c","-t","bbc",
                                  "-o",str(object_file),"src/main.c"],
                                  cwd=root,capture_output=True,text=True,
                                  timeout=75)
            assert check.returncode==0,(check.stdout,check.stderr)
            assert object_file.stat().st_size>256
            pytest.skip("BBC native object compiled; linker target bbc.lib "
                        "absent from installed cc65 distribution")
    c=subprocess.run(["make","-C",str(root)],capture_output=True,text=True,
                      timeout=100)
    assert c.returncode==0,(c.stdout,c.stderr)
    artifact=root/"build"/("dragon."+CLASSICS[target].output)
    assert artifact.exists() and artifact.stat().st_size>512
    # File format/container and actual hardware runtime differ. This test
    # proves a real target linker output exists; not launch/playability.
    assert artifact.read_bytes()!=files["src/main.c"].encode()
