"""Actual game save/resume: native C runtime corruption and foreign-campaign tests."""
from __future__ import annotations
import shutil,subprocess,pytest
from skeleton.ai.webcrawler.dragon_native_puzzle import emit_native_puzzle
from skeleton.ai.webcrawler.dragon_native_puzzle_save import enable_native_save,SOURCE
from skeleton.ai.webcrawler.dragon_native_puzzle_trace import enable_native_trace
from skeleton.ai.webcrawler.dragon_native_puzzle_challenge import enable_native_challenge
from skeleton.ai.webcrawler.dragon_native_puzzle_hints import enable_live_hints

def test_generated_native_game_has_real_local_save_resume():
    source=emit_native_puzzle(seed=5,stages=2)["src/main.c"]
    assert 'DRAGON_SAVE_NAME "dragon-save-v1.dat"' in source
    assert "write_local_original_save" in source
    assert "read_local_original_save" in source
    assert "game_map_fingerprint" in source
    assert "original_save_selftest" in source
    assert "if(key=='k'||key=='K')" in source
    assert "if(key=='l'||key=='L')" in source
    assert "--save-selftest" in source
    assert "DRAGON_NATIVE_SAVE_SELFTEST PASS" in source

def test_save_module_will_not_write_into_missing_or_untrusted_source():
    with pytest.raises(ValueError):
        enable_native_save("int main(int argc,char**argv){}")
    for bad in ("",None,123):
        with pytest.raises(ValueError):
            enable_native_save(bad)

@pytest.mark.skipif(not shutil.which("cc"),reason="requires real native C99 compiler")
@pytest.mark.parametrize("seed,stages",[(1,1),(37,3),(2026,8)])
def test_compiled_original_game_saves_and_reloads_actual_crate_player_state(
    tmp_path,seed,stages,
):
    output=emit_native_puzzle(seed=seed,stages=stages,difficulty=7)
    (tmp_path/"src").mkdir();(tmp_path/"include").mkdir()
    (tmp_path/"src/main.c").write_text(output["src/main.c"])
    (tmp_path/"include/dragon_puzzle.h").write_text(output["include/dragon_puzzle.h"])
    compiler=subprocess.run(
        ["cc","-std=c99","-O2","-Wall","-Wextra","-Werror",
         "-pedantic","-Iinclude","src/main.c","-o","dragon_game"],
        cwd=tmp_path,capture_output=True,text=True,timeout=40,
    )
    assert compiler.returncode==0,compiler.stderr
    run=subprocess.run(
        [str(tmp_path/"dragon_game"),"--save-selftest"],
        cwd=tmp_path,capture_output=True,text=True,timeout=20,
    )
    assert run.returncode==0,(run.stdout,run.stderr)
    assert "DRAGON_NATIVE_SAVE_SELFTEST PASS" in run.stdout
    assert not (tmp_path/"dragon-save-v1.dat").exists()
    assert not (tmp_path/"dragon-save-v1.tmp").exists()


@pytest.mark.skipif(not shutil.which("cc"),reason="requires native C99 compiler")
def test_in_game_save_and_resume_controls_operate_on_original_interactive_game(tmp_path):
    project=emit_native_puzzle(seed=99,stages=1)
    (tmp_path/"src").mkdir();(tmp_path/"include").mkdir()
    (tmp_path/"src/main.c").write_text(project["src/main.c"])
    (tmp_path/"include/dragon_puzzle.h").write_text(project["include/dragon_puzzle.h"])
    compiler=subprocess.run(["cc","-std=c99","-Iinclude","src/main.c",
                             "-o","dragon_game"],cwd=tmp_path,
                            capture_output=True,text=True,timeout=40)
    assert compiler.returncode==0,compiler.stderr
    result=subprocess.run(
        [str(tmp_path/"dragon_game")],
        cwd=tmp_path,input="d\nk\nw\nl\nq\n",
        capture_output=True,text=True,timeout=15,
    )
    assert result.returncode==0,(result.stdout,result.stderr)
    assert "Local original game saved: yes" in result.stdout
    assert "Local original game resumed: yes" in result.stdout
    assert (tmp_path/"dragon-save-v1.dat").is_file()



def test_second_native_game_save_uses_platform_safe_replacement():
    from skeleton.ai.webcrawler.dragon_native_puzzle_save import SOURCE
    assert "MoveFileExA(temp,target,MOVEFILE_REPLACE_EXISTING" in SOURCE
    assert "MOVEFILE_WRITE_THROUGH" in SOURCE
    assert "#ifdef _WIN32" in SOURCE
    assert "return rename(temp,target)==0;" in SOURCE
    assert "replace_local_original_save(DRAGON_TEMP_NAME,DRAGON_SAVE_NAME)" in SOURCE
