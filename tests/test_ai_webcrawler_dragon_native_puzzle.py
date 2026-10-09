"""Source-bound original Sokoban generation and real C99 executable test.

This is a dependency-free actual native game: a C compiler executes the
selected original game, verifies every level through the real push/collision
state machine, and rejects tampered/invalid abstract grid levels.
"""
from __future__ import annotations
from hashlib import sha256
import json,os,subprocess,shutil
import pytest
from skeleton.ai.webcrawler.dragon_native_puzzle import (
    BASE_LEVELS,MAX_SEARCH,MAX_SOLUTION,
    solve_grid,transformed_level,emit_native_puzzle,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_game_design import starter_design,parse_design
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

def project(*,target="pc_linux",design=None):
    return render_native_project(title=design.title if design else "Dragon Sokoban",
        target_id=target,style="fixed_screen_puzzle",
        candidate_id=sha256(b"native_c_puzzle").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True,
        design=design)

@pytest.mark.parametrize("seed",[0,1,0xDEADBEEF,2026,29])
@pytest.mark.parametrize("stage",range(8))
def test_every_transformed_original_puzzle_has_a_bounded_shortest_walk(seed,stage):
    grid=transformed_level(stage,seed)
    assert len(grid)==10 and all(len(r)==12 for r in grid)
    assert sum(r.count("@") for r in grid)==1
    assert sum(r.count("$") for r in grid)==sum(r.count("o") for r in grid)
    trace,states=solve_grid(grid)
    assert 1<=len(trace)<MAX_SOLUTION
    assert 1<=states<MAX_SEARCH
    assert all(m in "wasd" for m in trace)
    assert solve_grid(grid)==(trace,states)

def test_exact_solver_fails_closed_for_corrupt_levels():
    with pytest.raises(ValueError):
        solve_grid(("x"*12,)*10)
    with pytest.raises(ValueError):
        solve_grid(BASE_LEVELS[0][:4])
    with pytest.raises(ValueError):
        transformed_level(8,123)
    with pytest.raises(ValueError):
        transformed_level(2,-1)
    with pytest.raises(ValueError):
        transformed_level(2,1,difficulty=11)

def test_real_pc_puzzle_game_exposes_true_native_and_compiled_solution():
    p=project()
    assert "src/main.c" in p.files
    assert "include/dragon_puzzle.h" in p.files
    assert "Makefile" in p.files and "CMakeLists.txt" in p.files
    assert "SDL" not in p.files["src/main.c"]
    assert "UNDO_MAX" in p.files["src/main.c"]
    assert "static int perform(char key)" in p.files["src/main.c"]
    assert "static void rollback(void)" in p.files["src/main.c"]
    assert "static int selftest(void)" in p.files["src/main.c"]
    assert "DRAGON_NATIVE_PUZZLE_SELFTEST PASS" in p.files["src/main.c"]
    assert "dragon_solution_length" in p.files["include/dragon_puzzle.h"]
    assert p.status=="source_generated"
    plan=json.loads(p.files["dragon-puzzle-proof.json"])
    assert plan["stages"]==4
    assert plan["mode"]=="original_native_sokoban"
    assert all(item["optimal_within_abstract_grid"] for item in plan["level_proofs"])
    assert all(item["steps"]==len(item["solution"]) for item in plan["level_proofs"])
    manifest=json.loads(p.files["dragon-native-manifest.json"])
    assert manifest["runtime_gameplay_mode"]=="native_original_sokoban"
    by_id={t["id"]:t for t in target_catalog()}
    for target in ("pc_linux","pc_windows","pc_macos","steam_deck"):
        assert "fixed_screen_puzzle" in by_id[target]["supported_styles"]

def test_custom_design_controls_actual_stages_and_puzzle_difficulty():
    data=starter_design(genre="fixed_screen_puzzle",target="pc_linux",seed=24)
    data["stages"]=6
    data["difficulty"]=2
    a=project(design=parse_design(data))
    data["difficulty"]=10
    b=project(design=parse_design(data))
    a_plan=json.loads(a.files["dragon-puzzle-proof.json"])
    b_plan=json.loads(b.files["dragon-puzzle-proof.json"])
    assert len(a_plan["level_proofs"])==6
    assert len(b_plan["level_proofs"])==6
    assert a_plan["level_proofs"][0]["crates"]==1
    assert b_plan["level_proofs"][0]["crates"]==2
    assert a.digest!=b.digest
    assert "dragon-game-design.json" in b.files

def test_native_c99_compilation_and_actual_solution_replay(tmp_path):
    if not shutil.which("cc") or not shutil.which("cmake"):
        pytest.skip("native C compiler or CMake absent")
    design=parse_design(starter_design(
        title="Dragon Puzzle Factory",genre="fixed_screen_puzzle",seed=2026))
    output=tmp_path/"puzzle"
    emit_demo("pc_linux",output,design=design)
    configure=subprocess.run(["cmake","-S",str(output),"-B",str(output/"build")],
        timeout=40,capture_output=True,text=True)
    assert configure.returncode==0,configure.stderr
    compile=subprocess.run(["cmake","--build",str(output/"build"),"-j","2"],
        timeout=40,capture_output=True,text=True)
    assert compile.returncode==0,compile.stderr
    binary=output/"build"/"dragon_game"
    assert binary.is_file()
    tested=subprocess.run([str(binary),"--selftest"],timeout=10,
        capture_output=True,text=True)
    assert tested.returncode==0,(tested.stdout,tested.stderr)
    assert "DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=4" in tested.stdout
    assert tested.stdout.count("PUZZLE_STAGE_PASS")==4
    states=subprocess.run([str(binary),"--list"],timeout=10,
        capture_output=True,text=True)
    assert states.returncode==0
    assert states.stdout.count("solution_moves=")==4
    keyboard=subprocess.run([str(binary)],input="h\nq\n",
        capture_output=True,text=True,timeout=10)
    assert keyboard.returncode==0
    assert "Canonical first input:" in keyboard.stdout
