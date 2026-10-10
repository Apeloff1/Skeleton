"""Compiled original homebrew solver: shortest hints from ACTUAL crate positions."""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
import pytest

from skeleton.ai.webcrawler.dragon_native_puzzle_hints import (
    enable_live_hints, SOLVER,
)
from skeleton.ai.webcrawler.dragon_native_puzzle import (
    C_SOURCE, emit_native_puzzle, solve_grid, transformed_level,
)

def test_native_c_game_embeds_bounded_sokoban_shortest_solver():
    generated=emit_native_puzzle(seed=17,stages=5,difficulty=6)
    runtime=generated["src/main.c"]
    assert "HINT_NODES 50000" in runtime
    assert "HINT_BUCKETS 131071" in runtime
    assert "shortest_hint()" in runtime
    assert "HintNode" in runtime
    assert "current position" in runtime
    assert "--hint-selftest" in runtime
    assert "Restart to view canonical opening move" not in runtime
    from skeleton.ai.webcrawler.dragon_native_puzzle_trace import enable_native_trace
    assert runtime==enable_native_trace(enable_live_hints(C_SOURCE))
    assert generated==emit_native_puzzle(seed=17,stages=5,difficulty=6)

def test_hint_insertion_refuses_changed_or_incomplete_native_runtime():
    for bad in ("no native C gameplay", C_SOURCE.replace("static void draw(void){","bad draw(void){"),
                C_SOURCE.replace("Canonical first input: %c","fake opening hint: %c")):
        with pytest.raises(ValueError):
            enable_live_hints(bad)

def test_original_puzzle_shortest_solver_expected_native_move_order():
    assert "const char keys[4]={'a','d','w','s'};" in SOLVER
    assert "hint_same(n,&nodes[seen],state.count)" in SOLVER
    assert "hint_sort(&next,state.count)" in SOLVER
    for seed in (0,1,17,322,0xDEADBEEF):
        grid=transformed_level(3,seed,difficulty=8)
        solution,states=solve_grid(grid)
        assert solution and 0<states<120000

@pytest.mark.skipif(not shutil.which("cc"),reason="requires local native C99 compiler")
@pytest.mark.parametrize("stages,difficulty,seed", [
    (1,1,0),(2,4,17),(4,8,1977),(8,10,2001),
])
def test_live_hints_real_executable_replays_solutions(tmp_path,stages,difficulty,seed):
    files=emit_native_puzzle(seed=seed,stages=stages,difficulty=difficulty)
    source=tmp_path/"src"
    include=tmp_path/"include"
    source.mkdir();include.mkdir()
    (source/"main.c").write_text(files["src/main.c"],encoding="utf-8")
    (include/"dragon_puzzle.h").write_text(files["include/dragon_puzzle.h"],encoding="utf-8")
    exe=tmp_path/"dragon_game"
    command=["cc","-std=c99","-O2","-Wall","-Wextra","-Werror",
             "-pedantic","-Iinclude","src/main.c","-o",str(exe)]
    output=subprocess.run(command,cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert output.returncode==0,output.stderr
    runtime=subprocess.run([str(exe),"--hint-selftest"],cwd=tmp_path,
                           capture_output=True,text=True,timeout=60)
    assert runtime.returncode==0,(runtime.stdout,runtime.stderr)
    assert runtime.stdout.count("PUZZLE_HINT_PASS level=")==stages
    assert f"DRAGON_NATIVE_PUZZLE_HINTS PASS stages={stages}" in runtime.stdout
    opening=subprocess.run([str(exe)],input="h\nq\n",cwd=tmp_path,
                           capture_output=True,text=True,timeout=15)
    assert opening.returncode==0
    assert "Next shortest move from current position:" in opening.stdout
