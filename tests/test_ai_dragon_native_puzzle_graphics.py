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
    assert "#include <SDL.h>" not in source_game()["src/main.c"]
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
    graph=json.loads(files["dragon-puzzle-proof.json"])["campaign_graph"]
    actual_forks=sum(len(chapter["exits"]) for chapter in graph["chapters"])
    assert run.stdout.count("DRAGON_SDL_BRANCH_PASS from=")==actual_forks
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
    from skeleton.ai.webcrawler.dragon_native_puzzle_capture import enable_sdl_original_game_capture
    from skeleton.ai.webcrawler.dragon_native_puzzle_hud import enable_original_native_hud
    assert sources["src/graphics.c"]==enable_sdl_original_game_capture(
        enable_original_native_hud(C_GRAPHICS)
    )
    # Match the original authored seed used by this source release.
    assert sources["include/dragon_puzzle_pixels.h"]==pixel_header(seed=17)



@pytest.mark.skipif(not shutil.which("cc") or not shutil.which("pkg-config"),
                    reason="requires actual local SDL2 compiler")
def test_native_game_screenshots_are_real_gameplay_frames_with_bmp_structure(tmp_path):
    import struct
    available=subprocess.run(["pkg-config","--exists","sdl2"],timeout=8)
    if available.returncode!=0:
        pytest.skip("SDL2 development library not installed")
    files=source_game(seed=37,stages=2)
    for name,content in files.items():
        file=tmp_path/name
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(content)
    compiled=subprocess.run(["make","graphics"],cwd=tmp_path,
                            capture_output=True,text=True,timeout=35)
    assert compiled.returncode==0,compiled.stderr
    folder=tmp_path/"frames"
    folder.mkdir()
    output=subprocess.run(
        [str(tmp_path/"dragon_game_sdl"),"--capture-frames",str(folder)],
        cwd=tmp_path,capture_output=True,text=True,
        env={**os.environ,"SDL_VIDEODRIVER":"dummy",
             "SDL_AUDIODRIVER":"dummy"},timeout=40,
    )
    assert output.returncode==0,(output.stdout,output.stderr)
    assert output.stdout.count("DRAGON_SDL_FRAME level=")==6
    assert "DRAGON_SDL_CAPTURE_PASS stages=2 frames=6" in output.stdout
    images=sorted(folder.glob("*.bmp"))
    assert len(images)==6
    assert images[0].name=="level-01-frame-00.bmp"
    assert images[-1].name=="level-02-frame-02.bmp"
    for path in images:
        raw=path.read_bytes()
        assert raw[:2]==b"BM"
        assert struct.unpack_from("<I",raw,18)[0]==640
        assert struct.unpack_from("<I",raw,22)[0]==480
        assert len(raw)<3_000_000
    assert images[0].read_bytes()!=images[2].read_bytes()



def test_original_creator_changes_genuine_graphical_native_avatar_and_biome_tiles():
    from skeleton.ai.webcrawler.dragon_native_puzzle_graphics import pixel_header
    modern=pixel_header(hero="astronaut",theme="space",
                        palette="modern_neon",seed=37)
    original=pixel_header(hero="hatchling",theme="ancient_ruins",
                          palette="dmg_green",seed=37)
    assert modern!=original
    assert modern.count("static const uint8_t")==4
    assert len(modern)<5000
    request=ProductionRequest(
        title="Original Galaxy Native Puzzles",
        style="fixed_screen_puzzle",targets=("pc_linux",),
        seed=37,original_work_attested=True,
        portable_design=PortableGameDesign(
            hero="astronaut",quest_theme="space",palette="modern_neon",
            stages=2,
        ),
    )
    project=_render(request,"pc_linux")
    assert project.files["include/dragon_puzzle_pixels.h"]==modern
    source,_=make_source_release(project,request)
    receipt,files=_puzzle_proof(source)
    assert receipt["style"]=="fixed_screen_puzzle"
    assert files["include/dragon_puzzle_pixels.h"]==modern


def test_native_visual_replay_detects_a_replaced_hero_tile_even_in_valid_source_release():
    from dataclasses import replace
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    from skeleton.ai.webcrawler.dragon_native_puzzle_graphics import pixel_header
    game=ProductionRequest(
        title="Original Actor Runtime",
        style="fixed_screen_puzzle",targets=("pc_linux",),seed=41,
        original_work_attested=True,
        portable_design=PortableGameDesign(
            hero="robot",quest_theme="volcano",stages=1,
        ),
    )
    expected=_render(game,"pc_linux")
    fake=dict(expected.files)
    fake["include/dragon_puzzle_pixels.h"]=pixel_header(
        hero="hatchling",theme="forest",palette="dmg_green",seed=41)
    manipulated=replace(expected,files=fake,digest=digest(fake))
    source,_=make_source_release(manipulated,game)
    with pytest.raises(ValueError,match="native runnable source"):
        _puzzle_proof(source)



def test_sdl_native_hud_uses_actual_game_state_not_simulated_reward_values():
    from skeleton.ai.webcrawler.dragon_native_puzzle_hud import enable_original_native_hud
    runtime=enable_original_native_hud(C_GRAPHICS)
    assert "int stars=native_puzzle_stars();" in runtime
    assert "for(int i=0;i<state.count;i++)" in runtime
    assert "if(goals[state.boxes[i]])placed++;" in runtime
    assert "int minimum=dragon_solution_length[chapter];" in runtime
    assert "if(level_done())" in runtime
    assert "for(int i=0;i<LEVEL_COUNT;i++)" in runtime
    assert "paint=n<stars?completed:missing" in runtime
    with pytest.raises(ValueError):
        enable_original_native_hud(runtime)


def test_all_original_graphical_games_ship_native_hud_and_true_pixel_frame_capture():
    from skeleton.ai.webcrawler.dragon_native_puzzle_hud import HUD_C
    generated=source_game(seed=2026,stages=3)
    runtime=generated["src/graphics.c"]
    assert HUD_C in runtime
    assert "capture_solver_frames" in runtime
    assert "DRAGON_SDL_RENDER_GAMEPLAY_PASS" in runtime
