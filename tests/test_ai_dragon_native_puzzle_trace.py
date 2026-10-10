"""Verify native C99 gameplay state converges with independent grid physics."""
from __future__ import annotations
import shutil,subprocess
from hashlib import sha256
import pytest
from skeleton.ai.webcrawler.dragon_native_puzzle import (
    emit_native_puzzle,transformed_level,solve_grid,
)
from skeleton.ai.webcrawler.dragon_native_puzzle_trace import (
    _native_hash,simulate_grid,parse_native_state_line,enable_native_trace,
    MAX_SEQUENCE,
)

def test_independent_puzzle_replay_is_deterministic_and_sensitive_to_moves():
    grid=transformed_level(0,17,4)
    trace,states=solve_grid(grid)
    a=simulate_grid(grid,trace)
    b=simulate_grid(grid,"r"+trace)
    assert a==b
    assert a.solved and a.moves==len(trace)
    assert a.digest==b.digest and len(a.digest)==8
    changed=simulate_grid(grid,trace[:1])
    assert changed.digest!=a.digest
    assert not changed.solved

def test_independent_puzzle_replay_undo_and_reset_restore_canonical_state():
    grid=transformed_level(2,11,7)
    initial=simulate_grid(grid,"")
    for inputs in ("a"+"u","d"+"u","w"+"u","s"+"u","wwaaddr"+"r",
                   "a"+"u"+"r","s"+"u"+"r"):
        result=simulate_grid(grid,inputs)
        assert result==initial or inputs.endswith("r"), inputs
    assert simulate_grid(grid,"wasd"+"r")==initial

@pytest.mark.parametrize("invalid",[
    "x", "q", "h", "w"*401, "w\na", "🧙",
])
def test_puzzle_replay_does_not_accept_unknown_unbounded_commands(invalid):
    with pytest.raises(ValueError):
        simulate_grid(transformed_level(0,0),invalid)

def test_puzzle_runtime_state_parser_is_bounded_and_rejects_fake_success():
    valid="DRAGON_NATIVE_STATE level=2 player=43 crates=51,52 moves=12 pushes=4 solved=0 digest=1234abcd\n"
    assert parse_native_state_line(valid)=={
        "level":2,"player":43,"crates":(51,52),
        "moves":12,"pushes":4,"solved":False,"digest":"1234abcd",
    }
    for invalid in ("",valid+"FAKE",valid.replace("digest=","rom_certified=1 digest="),
                    valid.replace("level=2","level=99")):
        with pytest.raises(ValueError):
            parse_native_state_line(invalid)

def test_c99_headless_physics_interface_is_actually_inserted():
    source=emit_native_puzzle(seed=1,stages=4)["src/main.c"]
    assert "static int simulate_native_inputs" in source
    assert '--simulate' in source
    assert "static uint32_t state_hash" in source
    assert "HINT_BUCKETS 131071" in source
    assert "if(action=='u'){rollback();continue;}" in source

@pytest.mark.skipif(not shutil.which("cc"),reason="requires local C99 compiler")
@pytest.mark.parametrize("seed,difficulty,stages",[(1,2,1),(5,5,4),(1977,10,8)])
def test_compiled_game_state_exactly_matches_original_grid_physics(
    tmp_path,seed,difficulty,stages,
):
    native=emit_native_puzzle(seed=seed,difficulty=difficulty,stages=stages)
    (tmp_path/"src").mkdir();(tmp_path/"include").mkdir()
    (tmp_path/"src/main.c").write_text(native["src/main.c"])
    (tmp_path/"include/dragon_puzzle.h").write_text(native["include/dragon_puzzle.h"])
    output=subprocess.run(
        ["cc","-std=c99","-O2","-Wall","-Wextra","-Werror",
         "-pedantic","-Iinclude","src/main.c","-o","dragon_game"],
        cwd=tmp_path,capture_output=True,text=True,timeout=30,
    )
    assert output.returncode==0,output.stderr
    game=tmp_path/"dragon_game"
    for level in range(1,stages+1):
        grid=transformed_level(level-1,seed,difficulty)
        solution,_=solve_grid(grid)
        for events in (solution,"r"+solution,solution[:5]+"r"+solution,
                       "su"+solution,"wwa"+"r"+solution):
            model=simulate_grid(grid,events,level=level)
            executed=subprocess.run(
                [str(game),"--simulate",str(level),events],
                cwd=tmp_path,capture_output=True,text=True,timeout=15,
            )
            assert executed.returncode==0,(executed.stderr,executed.stdout)
            actual=parse_native_state_line(executed.stdout)
            assert actual["digest"]==model.digest
            assert actual["player"]==model.player
            assert actual["crates"]==model.crates
            assert actual["solved"]==model.solved
            assert actual["moves"]==model.moves
            assert actual["pushes"]==model.pushes
