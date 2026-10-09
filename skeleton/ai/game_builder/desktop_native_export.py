"""Produce a native SDL2/C11 game project from a validated ORIGINAL world.

This exporter produces actual C source, a CMake native build target and a sealed
manifest, not HTML or a browser wrapper. It does not claim that a compiler, SDL2
runtime, installer, code-signing keys or a runnable .exe exist on the host.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_world import PlayableWorld
from .playable_simulation import demonstrate_solvable
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

_DESKTOP_TARGETS = frozenset({"windows_modern", "linux_desktop", "macos_modern"})
_CMAKE = """cmake_minimum_required(VERSION 3.16)
project(SkeletonOriginalHomebrew LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
add_executable(skeleton_homebrew game.c)
find_package(SDL2 CONFIG QUIET)
if(TARGET SDL2::SDL2)
  target_link_libraries(skeleton_homebrew PRIVATE SDL2::SDL2)
elseif(TARGET SDL2::SDL2-static)
  target_link_libraries(skeleton_homebrew PRIVATE SDL2::SDL2-static)
else()
  find_package(PkgConfig QUIET)
  if(NOT PkgConfig_FOUND)
    message(FATAL_ERROR "Provide the SDL2 development library (vcpkg or pkg-config)")
  endif()
  pkg_check_modules(SDL2 REQUIRED IMPORTED_TARGET sdl2)
  target_link_libraries(skeleton_homebrew PRIVATE PkgConfig::SDL2)
endif()
"""

_C_GAME = r"""
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

/* Original maze game. No third-party ROM, game code, firmware or assets. */
#define LEVEL_COUNT __LEVEL_COUNT__
#define MAP_WIDTH __MAP_WIDTH__
#define MAP_HEIGHT __MAP_HEIGHT__
#define MAX_MAP_DIM 41
static const char *const map_data[LEVEL_COUNT][MAP_HEIGHT] = {
__MAP_DATA__
};
static const char game_title[] = __TITLE__;
static const int initial_health = __INITIAL_HEALTH__;
static bool claimed[LEVEL_COUNT][MAX_MAP_DIM][MAX_MAP_DIM];
static int current_level = 0;
static int px = 1, py = 1, hp = 3, score = 0, moves = 0, found = 0;
static bool won = false, lost = false;

static char tile_at(int level, int x, int y) {
    if (x < 0 || x >= MAP_WIDTH || y < 0 || y >= MAP_HEIGHT) return '#';
    return map_data[level][y][x];
}
static int collectible_total(int level) {
    int n = 0;
    for (int y = 0; y < MAP_HEIGHT; ++y)
        for (int x = 0; x < MAP_WIDTH; ++x)
            if (tile_at(level, x, y) == 'C') ++n;
    return n;
}
static void enter_level(void) {
    found = 0;
    for (int y = 0; y < MAP_HEIGHT; ++y)
        for (int x = 0; x < MAP_WIDTH; ++x)
            if (tile_at(current_level, x, y) == 'S') { px = x; py = y; return; }
}
static void restart_game(void) {
    memset(claimed, 0, sizeof(claimed));
    hp = initial_health; moves = 0; score = 0; current_level = 0;
    won = false; lost = false;
    enter_level();
}
static void walk(int dx, int dy) {
    if (won || lost) return;
    int nx = px + dx, ny = py + dy;
    char tile = tile_at(current_level, nx, ny);
    ++moves;
    if (tile == '#') return;
    px = nx; py = ny;
    if (tile == 'C' && !claimed[current_level][py][px]) {
        claimed[current_level][py][px] = true;
        ++found; score += 10;
    } else if (tile == 'H') {
        if (--hp <= 0) { hp = 0; lost = true; return; }
    }
    if (tile == 'G' && found >= collectible_total(current_level)) {
        score += 100;
        if (current_level + 1 >= LEVEL_COUNT) won = true;
        else { ++current_level; enter_level(); }
    }
}
static void fill(SDL_Renderer *renderer, int x, int y, int w, int h,
                 unsigned char r, unsigned char g, unsigned char b) {
    SDL_Rect rc = {x, y, w, h};
    SDL_SetRenderDrawColor(renderer, r, g, b, 255);
    SDL_RenderFillRect(renderer, &rc);
}
static void render(SDL_Renderer *renderer, int tile_size) {
    SDL_SetRenderDrawColor(renderer, 12, 23, 37, 255);
    SDL_RenderClear(renderer);
    for (int y = 0; y < MAP_HEIGHT; ++y) for (int x = 0; x < MAP_WIDTH; ++x) {
        char tile = tile_at(current_level, x, y);
        const int ox = x * tile_size, oy = y * tile_size;
        fill(renderer, ox, oy, tile_size, tile_size, 22, 43, 58);
        if (tile == '#') fill(renderer, ox + 1, oy + 1, tile_size - 2, tile_size - 2, 64, 103, 128);
        else if (tile == 'G') fill(renderer, ox + 3, oy + 3, tile_size - 6, tile_size - 6, 231, 182, 83);
        else if (tile == 'H') fill(renderer, ox + 5, oy + 5, tile_size - 10, tile_size - 10, 227, 94, 111);
        else if (tile == 'C' && !claimed[current_level][y][x]) {
            int pulse = (int)((SDL_GetTicks() / 250u) % 3u);
            fill(renderer, ox + 5 + pulse, oy + 5 + pulse,
                 tile_size - 10 - 2 * pulse, tile_size - 10 - 2 * pulse, 111, 234, 195);
        }
    }
    int bob = (int)((SDL_GetTicks() / 350u) % 2u);
    fill(renderer, px * tile_size + 3, py * tile_size + 3 + bob,
         tile_size - 6, tile_size - 6, 250, 241, 208);
    SDL_RenderPresent(renderer);
}
static void keyboard(SDL_Keycode key) {
    switch (key) {
        case SDLK_UP: case SDLK_w: walk(0, -1); break;
        case SDLK_DOWN: case SDLK_s: walk(0, 1); break;
        case SDLK_LEFT: case SDLK_a: walk(-1, 0); break;
        case SDLK_RIGHT: case SDLK_d: walk(1, 0); break;
        case SDLK_r: restart_game(); break;
        default: break;
    }
}
int main(void) {
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER) != 0) {
        fprintf(stderr, "SDL initialization: %s\n", SDL_GetError());
        return 1;
    }
    int tile_size = 24;
    while (tile_size * MAP_WIDTH > 1160 || tile_size * MAP_HEIGHT > 820) --tile_size;
    if (tile_size < 14) tile_size = 14;
    SDL_Window *window = SDL_CreateWindow(game_title, SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED, tile_size * MAP_WIDTH, tile_size * MAP_HEIGHT, SDL_WINDOW_SHOWN);
    if (!window) { fprintf(stderr, "Window: %s\n", SDL_GetError()); SDL_Quit(); return 2; }
    SDL_Renderer *renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer) { SDL_DestroyWindow(window); SDL_Quit(); return 3; }
    SDL_GameController *pad = NULL;
    for (int i = 0; i < SDL_NumJoysticks(); ++i)
        if (SDL_IsGameController(i)) { pad = SDL_GameControllerOpen(i); break; }
    restart_game();
    bool running = true;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = false;
            else if (event.type == SDL_KEYDOWN && !event.key.repeat) {
                if (event.key.keysym.sym == SDLK_ESCAPE) running = false;
                else keyboard(event.key.keysym.sym);
            } else if (event.type == SDL_CONTROLLERBUTTONDOWN) {
                switch (event.cbutton.button) {
                    case SDL_CONTROLLER_BUTTON_DPAD_UP: walk(0, -1); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: walk(0, 1); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: walk(-1, 0); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: walk(1, 0); break;
                    case SDL_CONTROLLER_BUTTON_X: restart_game(); break;
                    default: break;
                }
            }
        }
        char caption[512];
        snprintf(caption, sizeof(caption), "%s | Level %d/%d | HP %d | Crystals %d/%d | Score %d | Moves %d%s",
            game_title, current_level + 1, LEVEL_COUNT, hp, found,
            collectible_total(current_level), score, moves,
            won ? " | CLEARED! Press R" : (lost ? " | GAME OVER - Press R" : ""));
        SDL_SetWindowTitle(window, caption);
        render(renderer, tile_size);
        SDL_Delay(16);
    }
    if (pad) SDL_GameControllerClose(pad);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
"""


class NativeDesktopExportError(ValueError):
    """A source world or target cannot be translated into native game sources."""


@dataclass(frozen=True, slots=True)
class NativeDesktopSourceProject:
    target_platform_id: str
    game_c: str
    cmake_lists: str
    manifest_json: str
    content_digest: str
    output_kind: str = "native_sdl2_source_project"
    binary_verified: bool = False


def _c_literal(value: str) -> str:
    """Escape UTF-8 into a C string, avoiding C unicode syntax and source injection."""
    out = ['"']
    for byte in value.encode("utf-8"):
        if byte == 34:
            out.append(r'\"')
        elif byte == 92:
            out.append(r'\\')
        elif 32 <= byte <= 126:
            out.append(chr(byte))
        else:
            out.append("\\%03o" % byte)
    return "".join(out) + '"'


def compile_native_desktop(
    world: PlayableWorld, source: HomebrewSource, target_platform_id: str, *,
    authorized: bool, 
) -> NativeDesktopSourceProject:
    """Produce deterministic SDL2/CMake source; compilation still needs SDL2."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native export requires explicit authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise NativeDesktopExportError("typed original world and rights-bound source required")
    if world.intent.project_id != source.project_id:
        raise NativeDesktopExportError("world/source project mismatch")
    if target_platform_id not in _DESKTOP_TARGETS:
        raise NativeDesktopExportError("native SDL2 exporter does not support this target")
    blueprint = compile_port(PortRequest((source,), target_platform_id, PortMode.ENHANCED))
    replay = demonstrate_solvable(world, authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise NativeDesktopExportError("generated world must have a winning deterministic replay")
    levels = world.levels
    if not levels or any(level.width != levels[0].width or level.height != levels[0].height for level in levels):
        raise NativeDesktopExportError("SDL2 exporter expects uniform validated level dimensions")
    width, height = levels[0].width, levels[0].height
    grid_data = ",\n".join("    {" + ", ".join(_c_literal(row) for row in level.rows) + "}" for level in levels)
    c_source = (
        _C_GAME.replace("__LEVEL_COUNT__", str(len(levels)))
        .replace("__MAP_WIDTH__", str(width))
        .replace("__MAP_HEIGHT__", str(height))
        .replace("__MAP_DATA__", grid_data)
        .replace("__TITLE__", _c_literal(world.intent.title))
        .replace("__INITIAL_HEALTH__", str(world.intent.starting_health))
    ).lstrip()
    manifest = {
        "schema": "skeleton.game_builder.native_desktop_source.v1",
        "target_platform_id": target_platform_id,
        "source_project_id": source.project_id,
        "source_platform_id": source.platform_id,
        "source_rights_evidence_sha256": source.evidence_sha256,
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "port_blueprint_digest": blueprint.digest,
        "levels": len(levels),
        "output_kind": "native_sdl2_source_project",
        "compiler_required": True,
        "sdl2_development_library_required": True,
        "executable_built": False,
        "releasable": False,
        "third_party_game_assets_embedded": False,
    }
    manifest_json = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    content_digest = sha256((
        c_source + "\0" + _CMAKE + "\0" + manifest_json
    ).encode("utf-8")).hexdigest()
    return NativeDesktopSourceProject(
        target_platform_id, c_source, _CMAKE, manifest_json, content_digest,
    )


def export_native_desktop_source(
    project: NativeDesktopSourceProject, destination: str | Path, *,
    authorized: bool,
) -> Path:
    """Write into a NEW directory only; refuses overwrite or implicit execution."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native source export requires explicit authorization")
    if not isinstance(project, NativeDesktopSourceProject):
        raise NativeDesktopExportError("typed native source project required")
    folder = Path(destination)
    # Do not overwrite existing projects or follow pre-existing directory links.
    if folder.exists() or folder.is_symlink():
        raise FileExistsError(str(folder))
    folder.mkdir(parents=True, exist_ok=False)
    for name, content in (
        ("game.c", project.game_c),
        ("CMakeLists.txt", project.cmake_lists),
        ("manifest.json", project.manifest_json),
    ):
        with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return folder
