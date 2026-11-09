"""Native Atari 400/800 48K-class 6502/ANTIC/GTIA/POKEY game export.

Original PlayableWorld levels become real Atari 8-bit DOS-loadable .XEX
sources using the documented cc65 'atari' runtime. The runtime drives the
OS 40-column screen via conio, reads STICK0 joystick shadow and plays original
POKEY tones. This is not a C64 binary relabelled as Atari and does not require
commercial game materials or proprietary OS images in the output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

MAX_WIDTH = 37
MAX_HEIGHT = 22
MAX_STAGES = 8
_TILE_INDEX = {".": 0, "S": 0, "#": 1, "C": 2, "H": 3, "G": 4}

_C = r"""/* Original Atari 8-bit standalone executable program, generated, not a ROM rip. */
#include <conio.h>
typedef unsigned char u8;
typedef unsigned int u16;
#define WIDTH __WIDTH__
#define HEIGHT __HEIGHT__
#define LEVELS __LEVELS__
#define GEMS __GEMS__
#define START_HEALTH __HEALTH__
#define CELLS (WIDTH * HEIGHT)
#define STICK0 (*(volatile u8*)0x0278) /* Atari OS joystick zero shadow. */
#define VCOUNT (*(volatile u8*)0xD40B) /* ANTIC vertical line counter. */
#define COLOR1 (*(volatile u8*)0x02C5) /* Atari OS playfield colour shadow. */
#define COLOR2 (*(volatile u8*)0x02C6)
#define AUDF1 (*(volatile u8*)0xD200) /* POKEY channel-1 frequency. */
#define AUDC1 (*(volatile u8*)0xD201) /* POKEY channel-1 volume/distortion. */
#define AUDCTL (*(volatile u8*)0xD208) /* POKEY audio control. */
#define T_FLOOR 0
#define T_WALL 1
#define T_GEM 2
#define T_HAZARD 3
#define T_GOAL 4

static const u8 original_levels[LEVELS][CELLS] = {
__MAPS__
};
static const u8 starting_x[LEVELS] = { __START_X__ };
static const u8 starting_y[LEVELS] = { __START_Y__ };
static const char original_tiles[5] = { '.', '#', '*', '!', '>' };
static u8 runtime_map[CELLS];
static u8 level, x, y, gems_left, health, won, lost, cooldown;
static u16 score;

static u16 cell_at(u8 cx, u8 cy) { return (u16)cy * WIDTH + cx; }

static void sound_note(u8 value) {
    AUDF1 = value;
    AUDC1 = 0xA8;  /* One quiet pure POKEY channel; own synthesized cue. */
}

static void wait_frame(void) {
    /* Line 90 occurs on both NTSC and PAL ANTIC frame layouts. */
    while (VCOUNT > 90) { }
    while (VCOUNT < 90) { }
}

static void draw_hud(void) {
    gotoxy(0, 0);
    cputs("ORIGINAL ATARI HOMEBREW LVL:");
    cputc((char)('0' + level + 1));
    cputs("  G:");
    cputc((char)('0' + gems_left));
    cputs(" HP:");
    cputc((char)('0' + health));
    gotoxy(0, 23);
    cputs("SCORE:");
    cputc((char)('0' + (score / 1000) % 10));
    cputc((char)('0' + (score / 100) % 10));
    cputc((char)('0' + (score / 10) % 10));
    cputc((char)('0' + score % 10));
    cputs("  JOYSTICK 1  ORIGINAL GAME ");
}

static void draw_cell(u8 cx, u8 cy) {
    u8 tile = runtime_map[cell_at(cx, cy)];
    gotoxy((u8)(cx + 1), (u8)(cy + 1));
    cputc(original_tiles[tile]);
}

static void draw_player(void) {
    gotoxy((u8)(x + 1), (u8)(y + 1));
    cputc('@');
}

static void load_level(void) {
    u16 pos;
    level = (u8)(level % LEVELS);
    gems_left = GEMS;
    x = starting_x[level];
    y = starting_y[level];
    clrscr();
    for (pos = 0; pos < CELLS; ++pos) {
        runtime_map[pos] = original_levels[level][pos];
    }
    for (pos = 0; pos < CELLS; ++pos) {
        draw_cell((u8)(pos % WIDTH), (u8)(pos / WIDTH));
    }
    draw_hud();
    draw_player();
}

static void move(u8 nx, u8 ny) {
    u16 index;
    u8 tile;
    if (nx >= WIDTH || ny >= HEIGHT) return;
    index = cell_at(nx, ny);
    tile = runtime_map[index];
    if (tile == T_WALL) return;
    draw_cell(x, y);
    x = nx;
    y = ny;
    if (tile == T_GEM) {
        runtime_map[index] = T_FLOOR;
        --gems_left;
        score = (u16)(score + 10);
        sound_note(40);
    } else if (tile == T_HAZARD) {
        if (health) --health;
        sound_note(120);
        if (!health) lost = 1;
    } else if (tile == T_GOAL && gems_left == 0) {
        score = (u16)(score + 100);
        if ((u8)(level + 1) >= LEVELS) {
            won = 1;
        } else {
            ++level;
            load_level();
            return;
        }
    }
    draw_player();
    draw_hud();
}

static void poll_joystick(void) {
    u8 stick;
    if (cooldown) { --cooldown; return; }
    stick = STICK0;
    if ((stick & 1) == 0) {
        if (y) move(x, (u8)(y - 1));
    } else if ((stick & 2) == 0) {
        move(x, (u8)(y + 1));
    } else if ((stick & 4) == 0) {
        if (x) move((u8)(x - 1), y);
    } else if ((stick & 8) == 0) {
        move((u8)(x + 1), y);
    } else {
        return;
    }
    cooldown = 7;
}

int main(void) {
    COLOR1 = 0x88; /* Distinct original blue-violet playfield colour. */
    COLOR2 = 0x04;
    AUDCTL = 0;
    AUDF1 = 0;
    AUDC1 = 0;
    level = 0;
    x = 0;
    y = 0;
    won = 0;
    lost = 0;
    cooldown = 0;
    score = 0;
    health = START_HEALTH;
    load_level();
    for (;;) {
        wait_frame();
        if (won) {
            gotoxy(1, 23);
            cputs("ALL ORIGINAL STAGES COMPLETE!");
            AUDC1 = 0;
        } else if (lost) {
            gotoxy(1, 23);
            cputs("GAME OVER - TRY AGAIN      ");
            AUDC1 = 0;
        } else {
            poll_joystick();
        }
    }
    return 0;
}
"""
_MAKEFILE = """CL65 ?= cl65
.PHONY: all clean
all: build/skeleton-original.xex
build/skeleton-original.xex: game.c
\tmkdir -p build
\t$(CL65) -t atari -O -o $@ game.c
clean:
\trm -rf build
"""


class Atari8BitNativeError(ValueError):
    """Authentic Atari 8-bit homebrew exceeds source or hardware envelope."""


@dataclass(frozen=True, slots=True)
class Atari8BitSourceProject:
    game_c: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_atari_8bit_6502_antic_gtia_pokey_xex_source"
    executable_built: bool = False
    emulator_gameplay_verified: bool = False
    physical_hardware_verified: bool = False


def compile_native_atari8(world: PlayableWorld, source: HomebrewSource, *, authorized: bool) -> Atari8BitSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Atari original game export requires explicit authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise Atari8BitNativeError("typed world and original-homebrew evidence required")
    if world.intent.project_id != source.project_id:
        raise Atari8BitNativeError("original world and rights ownership project mismatch")
    if world.intent.width > MAX_WIDTH or world.intent.height > MAX_HEIGHT or len(world.levels) > MAX_STAGES:
        raise Atari8BitNativeError("Atari 8-bit 40x24 display or gameplay budget exceeded")
    if world.intent.collectibles_per_level > 9 or world.intent.starting_health > 9:
        raise Atari8BitNativeError("Atari 8-bit digit HUD cannot render objective or health count")
    plan = compile_port(PortRequest((source,), "atari_400_800", PortMode.REVERSE_CONSTRAINED))
    winning = demonstrate_solvable(world, authorized=True)
    if winning.world_digest != world.digest or winning.final_state.status != "won":
        raise Atari8BitNativeError("game world lacks independent winning gameplay proof")
    maps = []
    for stage in world.levels:
        flat = [_TILE_INDEX[t] for line in stage.rows for t in line]
        if len(flat) != world.intent.width * world.intent.height:
            raise Atari8BitNativeError("original Atari maze has corrupted dimensions")
        maps.append("    {" + ", ".join(str(v) for v in flat) + "}")
    args = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVELS__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__MAPS__": ",\n".join(maps),
        "__START_X__": ", ".join(str(s.start[0]) for s in world.levels),
        "__START_Y__": ", ".join(str(s.start[1]) for s in world.levels),
    }
    c = _C
    for key, value in args.items():
        if c.count(key) != 1:
            raise Atari8BitNativeError("Atari native source rendering marker collision")
        c = c.replace(key, value)
    manifest = json.dumps({
        "schema": "skeleton.game_builder.atari8_native_source.v1",
        "project_id": source.project_id, "source_platform": source.platform_id,
        "target_platform": "atari_400_800",
        "hardware_envelope": "Atari 400/800 48KB-class with Atari OS text mode",
        "target_format": "atari_8bit_dos_loadable_xex",
        "world_digest": world.digest,
        "original_world_digest": world.digest,
        "winning_reference_digest": winning.digest,
        "rights_evidence_sha256": source.evidence_sha256,
        "design_blueprint_digest": plan.digest,
        "original_tile_art_only": True,
        "original_pokey_audio_only": True,
        "levels": len(world.levels), "width": world.intent.width,
        "height": world.intent.height,
        "playable_reference_actions": sum(len(level.safe_solution) for level in world.levels),
        "executable_built": False, "emulator_gameplay_verified": False,
        "physical_hardware_verified": False, "redistribution_approved": False,
    }, sort_keys=True, indent=2) + "\n"
    digest = sha256((c + "\0" + _MAKEFILE + "\0" + manifest).encode()).hexdigest()
    return Atari8BitSourceProject(c, _MAKEFILE, manifest, digest)


def export_native_atari8(project: Atari8BitSourceProject, output: str | Path, *, authorized: bool) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Atari 8-bit source requires explicit authorization")
    if not isinstance(project, Atari8BitSourceProject):
        raise Atari8BitNativeError("typed Atari native source required")
    root = Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True, exist_ok=False)
    for name, data in (("game.c",project.game_c),("Makefile",project.makefile),
                       ("manifest.json",project.manifest_json)):
        with (root/name).open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(data)
    return root
