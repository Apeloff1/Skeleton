"""Native original SDL2 graphical puzzle: same C99 physics, real pixels and input."""
from __future__ import annotations
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile
import os,shutil,subprocess,json,pytest

from skeleton.ai.webcrawler.dragon_native_puzzle import emit_native_puzzle
from skeleton.ai.webcrawler.dragon_native_puzzle_graphics import (
    pixel_header,enable_puzzle_graphics,C_GRAPHICS,
)
from skeleton.ai.webcrawler.dragon_native_desktop import _puzzle_proof
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,_render,make_source_release,
)

def source_game(seed=17,stages=4):
    return emit_native_puzzle(seed=seed,stages=stages,difficulty=6)

def test_graphical_game_reuses_exact_original_terminal_state_and_not_duplicate_physics():
    files=source_game()
    graphics=files["src/graphics.c"]
    assert "#include \"main.c\"" in graphics
    assert "static int perform(char key)" not in graphics
    assert "perform(solution[i])" in graphics
    assert "native_puzzle_stars()" in graphics
    assert "shortest_hint()" in graphics
    assert "SDL_CONTROLLER_BUTTON_DPAD" in graphics
    assert "SDLK_BACKSPACE" in graphics
    assert "SDL_RenderReadPixels" in graphics
    assert "DRAGON_SDL_RENDER_GAMEPLAY_PASS" in graphics
    assert "src/graphics.c" in files
    assert "include/dragon_puzzle_pixels.h" in files
    assert "dragon_game_sdl" in files["Makefile"]
    assert "DRAGON_SDL2_FOUND" in files["CMakeLists.txt"]

def test_original_pixel_art_is_real_bounded_8_by_8_runtime_source():
    header=pixel_header()
    for name in ("dragon","dragon_blink","dragon_walk","star"):
        assert f"dragon_pixel_{name}[64]" in header
    assert "const uint8_t" in header
    assert len(header)<5000
    assert source_game()["include/dragon_puzzle_pixels.h"]==header

def test_graphical_native_source_is_generated_deterministically_without_sdl_dependency():
    assert source_game(seed=1)==source_game(seed=1)
    assert "SDL" not in source_game()["src/main.c"]
    assert "SDL2" in source_game()["src/graphics.c"]

@pytest.mark.skipif(not shutil.which("cc") or not shutil.which("pkg-config"),
                    reason="requires compiler and native pkg-config")
@pytest.mark.parametrize("stages,seed",[(1,1),(4,1977),(8,1234)])
def test_real_sdl2_game_compiles_renders_frames_and_executes_original_level_solutions(
    tmp_path,stages,seed,
):
    exists=subprocess.run(
        ["pkg-config","--exists","sdl2"],capture_output=True,
        timeout=8,
    )
    if exists.returncode!=0:
        pytest.skip("native SDL2 development library is not installed")
    files=source_game(seed=seed,stages=stages)
    for name,body in files.items():
        destination=tmp_path/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(body)
    compile=subprocess.run(["make","graphics"],
                           cwd=tmp_path,capture_output=True,text=True,timeout=35)
    assert compile.returncode==0,compile.stderr
    executable=tmp_path/"dragon_game_sdl"
    assert executable.is_file()
    environment={**os.environ,"SDL_VIDEODRIVER":"dummy","SDL_AUDIODRIVER":"dummy"}
    run=subprocess.run([str(executable),"--render-selftest"],
                       cwd=tmp_path,capture_output=True,text=True,
                       env=environment,timeout=40)
    assert run.returncode==0,(run.stdout,run.stderr)
    assert run.stdout.count("DRAGON_SDL_STAGE_PASS level=")==stages
    assert run.stdout.strip().endswith(
        f"DRAGON_SDL_RENDER_GAMEPLAY_PASS stages={stages}")

def test_original_graphics_source_is_covered_by_independent_release_replay():
    item=ProductionRequest(
        title="Original Pixel Puzzle",style="fixed_screen_puzzle",
        targets=("pc_linux",),seed=17,original_work_attested=True,
        portable_design=PortableGameDesign(stages=2),
    )
    native=_render(item,"pc_linux")
    package,_=make_source_release(native,item)
    receipt,sources=_puzzle_proof(package)
    assert receipt["target"]=="pc_linux"
    assert sources["src/graphics.c"]==C_GRAPHICS
    assert sources["include/dragon_puzzle_pixels.h"]==pixel_header()
