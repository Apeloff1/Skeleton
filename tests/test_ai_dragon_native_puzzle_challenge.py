"""Original native game performance grading: deterministic, bounded and playable."""
from __future__ import annotations
import shutil,subprocess
from pathlib import Path
import pytest

from skeleton.ai.webcrawler.dragon_native_puzzle_challenge import (
    SCHEMA,grade,enable_native_challenge,
)
from skeleton.ai.webcrawler.dragon_native_puzzle import emit_native_puzzle

@pytest.mark.parametrize("shortest,moves,stars",[
    (10,10,3),(10,11,2),(10,12,2),(10,13,1),
    (4,4,3),(4,5,2),(4,6,1),(100,110,2),(100,150,1),
])
def test_original_challenge_medals_follow_exact_solver_optimal_moves(shortest,moves,stars):
    scored=grade(shortest,moves,2,solved=True)
    assert scored.schema==SCHEMA
    assert scored.stars==stars
    assert 0<scored.efficiency_percent<=100
    assert 0<=scored.bonus_score<=1300

def test_incomplete_original_game_never_earns_trophies_or_AI_XP():
    result=grade(10,300,5,solved=False)
    assert not result.completed
    assert result.stars==result.efficiency_percent==result.bonus_score==0

@pytest.mark.parametrize("inputs",[
    (0,1,0,True),(400,401,0,True),(10,5,6,True),
    (10,-1,0,False),(10,3,0,"yes"),(True,5,0,True),
])
def test_original_scoring_refuses_unproved_or_unbounded_gameplay(*inputs):
    with pytest.raises(ValueError):
        grade(inputs[0],inputs[1],inputs[2],solved=inputs[3])

def test_c99_native_runtime_includes_real_challenge_grading_and_selftest():
    file=emit_native_puzzle(seed=19,stages=3)["src/main.c"]
    assert "static int native_puzzle_stars(void)" in file
    assert "static int native_puzzle_efficiency(void)" in file
    assert "static int native_puzzle_bonus(void)" in file
    assert "DRAGON_NATIVE_CHALLENGE PASS stages=" in file
    assert "--challenge-selftest" in file
    assert "Optimal steps: %d" in file

@pytest.mark.skipif(not shutil.which("cc"),reason="requires trusted C99 compiler")
@pytest.mark.parametrize("seed,levels",[(1,1),(1977,4),(1000,8)])
def test_real_compiled_game_awards_three_stars_for_proven_optimal_paths(tmp_path,seed,levels):
    project=emit_native_puzzle(seed=seed,stages=levels,difficulty=7)
    (tmp_path/"src").mkdir();(tmp_path/"include").mkdir()
    (tmp_path/"src/main.c").write_text(project["src/main.c"])
    (tmp_path/"include/dragon_puzzle.h").write_text(project["include/dragon_puzzle.h"])
    compiled=subprocess.run(
        ["cc","-std=c99","-O2","-Wall","-Wextra",
         "-Werror","-pedantic","-Iinclude","src/main.c","-o","dragon_game"],
        cwd=tmp_path,capture_output=True,text=True,timeout=35,
    )
    assert compiled.returncode==0,compiled.stderr
    game=tmp_path/"dragon_game"
    result=subprocess.run([str(game),"--challenge-selftest"],cwd=tmp_path,
                          capture_output=True,text=True,timeout=40)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert result.stdout.count("PUZZLE_CHALLENGE_PASS level=")==levels
    assert result.stdout.endswith(f"DRAGON_NATIVE_CHALLENGE PASS stages={levels}\n")
