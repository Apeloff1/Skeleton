"""Generate a genuine Commodore 64 6510 + VIC-II + SID homebrew PRG.

The C64 is a *different machine* from NES/DMG. This adapter emits cc65 C
using the C64's actual screen/color memory, CIA joystick port 2, raster timing
and optional SID feedback. Every map, collectible, collision and level state
comes from the original validated PlayableWorld rather than demo placeholders.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_world import PlayableWorld
from .playable_simulation import demonstrate_solvable
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

_MAX_W = 37
_MAX_H = 23
_TILES = {".":0, "S":0, "#":1, "C":2, "H":3, "G":4}

_C = r"""/* Original, project-owned Commodore 64 C homebrew source (cc65). */
/* Standalone VIC-II, CIA port-2 joystick and SID; no third-party assets. */
typedef unsigned char u8;
typedef unsigned int u16;

#define SCREEN ((volatile u8*)0x0400)
#define COLOUR ((volatile u8*)0xD800)
#define BORDER (*(volatile u8*)0xD020)
#define BACKGROUND (*(volatile u8*)0xD021)
#define JOY2 (*(volatile u8*)0xDC00)
#define RASTER (*(volatile u8*)0xD012)
#define SID_VOL (*(volatile u8*)0xD418)
#define SID_FREQ_LO (*(volatile u8*)0xD400)
#define SID_FREQ_HI (*(volatile u8*)0xD401)
#define SID_ATTACK (*(volatile u8*)0xD405)
#define SID_SUSTAIN (*(volatile u8*)0xD406)
#define SID_CTRL (*(volatile u8*)0xD404)
#define W __WIDTH__
#define H __HEIGHT__
#define LEVELS __LEVELS__
#define GEMS __GEMS__
#define HEALTH_START __HEALTH__
#define CELLS (W * H)
#define T_FLOOR 0
#define T_WALL 1
#define T_GEM 2
#define T_HAZARD 3
#define T_GOAL 4

static const u8 game_maps[LEVELS][CELLS] = {
__MAPS__
};
static const u8 start_x[LEVELS] = { __START_X__ };
static const u8 start_y[LEVELS] = { __START_Y__ };
static const u8 tile_codes[5] = { 32, 160, 42, 88, 7 };
static const u8 tile_ink[5] = { 6, 14, 7, 2, 5 };
static u8 runtime_map[CELLS];
static u8 level, player_x, player_y, health, gems_left;
static u8 won, lost, last_joystick, cooldown;
static u16 score;

static u16 index_at(u8 x, u8 y) { return (u16)y * W + x; }
static u16 screen_at(u8 x, u8 y) { return ((u16)y + 1) * 40 + x + 1; }
static u8 screen_char(u8 letter) {
    if (letter >= 'A' && letter <= 'Z') return (u8)(letter - 'A' + 1);
    if (letter >= '0' && letter <= '9') return letter;
    return 32;
}
static void print_at(u8 x, const char* message) {
    u16 index = x;
    while (*message && index < 40) {
        SCREEN[index] = screen_char((u8)*message);
        COLOUR[index] = 1;
        ++index;
        ++message;
    }
}
static void show_digit(u8 x, u8 value) {
    SCREEN[x] = (u8)(48 + (value % 10));
    COLOUR[x] = 1;
}
static void header(void) {
    print_at(0, "MOON MAZE   LVL 00  GEMS 0  HP 0");
    show_digit(17, (u8)(level + 1));
    show_digit(18, (u8)LEVELS);
    show_digit(26, gems_left);
    show_digit(32, health);
    SCREEN[36] = 48 + (u8)((score / 10) % 10);
    SCREEN[37] = 48 + (u8)(score % 10);
    COLOUR[36] = 1;
    COLOUR[37] = 1;
}
static void draw_cell(u8 x, u8 y) {
    u16 screen_index = screen_at(x, y);
    u8 tile = runtime_map[index_at(x, y)];
    SCREEN[screen_index] = tile_codes[tile];
    COLOUR[screen_index] = tile_ink[tile];
}
static void draw_player(void) {
    u16 position = screen_at(player_x, player_y);
    SCREEN[position] = 16;  /* C64 screen-code 'P', project-owned tile glyph */
    COLOUR[position] = 1;
}
static void beep(u8 pitch) {
    SID_FREQ_LO = pitch;
    SID_FREQ_HI = 25;
    SID_ATTACK = 0;
    SID_SUSTAIN = 0xF2;
    SID_VOL = 0x0F;
    SID_CTRL = 0x21; /* triangle gate */
}
static void load_level(void) {
    u16 i;
    u16 spot;
    level = level % LEVELS;
    player_x = start_x[level];
    player_y = start_y[level];
    gems_left = GEMS;
    BORDER = 6;
    BACKGROUND = 6;
    for (i = 0; i < 1000; ++i) {
        SCREEN[i] = 32;
        COLOUR[i] = 1;
    }
    for (i = 0; i < CELLS; ++i) {
        runtime_map[i] = game_maps[level][i];
    }
    for (spot = 0; spot < (u16)W * H; ++spot) {
        draw_cell((u8)(spot % W), (u8)(spot / W));
    }
    header();
    draw_player();
}
static void try_move(u8 next_x, u8 next_y) {
    u16 index;
    u8 tile;
    if (next_x >= W || next_y >= H) return;
    index = index_at(next_x, next_y);
    tile = runtime_map[index];
    if (tile == T_WALL) return;
    draw_cell(player_x, player_y);
    player_x = next_x;
    player_y = next_y;
    if (tile == T_GEM) {
        runtime_map[index] = T_FLOOR;
        --gems_left;
        ++score;
        beep(60);
    } else if (tile == T_HAZARD) {
        if (health > 0) --health;
        beep(10);
        if (health == 0) lost = 1;
    } else if (tile == T_GOAL && gems_left == 0) {
        if ((u8)(level + 1) == LEVELS) {
            won = 1;
        } else {
            ++level;
            load_level();
            return;
        }
    }
    draw_player();
    header();
}
static void wait_frame(void) {
    /* PAL and NTSC raster both have line 248. Deterministic frame clock. */
    while (RASTER >= 248) { }
    while (RASTER < 248) { }
}
static void poll_input(void) {
    u8 joystick;
    if (cooldown) { --cooldown; return; }
    joystick = JOY2;
    if (joystick == last_joystick && (joystick & 15) == 15) return;
    last_joystick = joystick;
    if (!(joystick & 1)) {
        if (player_y) try_move(player_x, (u8)(player_y - 1));
    } else if (!(joystick & 2)) {
        try_move(player_x, (u8)(player_y + 1));
    } else if (!(joystick & 4)) {
        if (player_x) try_move((u8)(player_x - 1), player_y);
    } else if (!(joystick & 8)) {
        try_move((u8)(player_x + 1), player_y);
    }
    cooldown = 7;
}
int main(void) {
    level = 0;
    health = HEALTH_START;
    gems_left = GEMS;
    won = 0;
    lost = 0;
    score = 0;
    cooldown = 0;
    last_joystick = 15;
    SID_VOL = 0;
    load_level();
    for (;;) {
        wait_frame();
        if (won) {
            print_at(0, "YOU WON ORIGINAL MOON MAZE");
            BORDER = 5;
            SID_CTRL = 0;
        } else if (lost) {
            print_at(0, "TRY AGAIN NEXT ADVENTURE");
            BORDER = 2;
            SID_CTRL = 0;
        } else {
            poll_input();
        }
    }
    return 0;
}
"""
_MAKEFILE = """CL65 ?= cl65
.PHONY: all clean
all: build/skeleton-original.prg
build/skeleton-original.prg: game.c
\tmkdir -p build
\t$(CL65) -t c64 -O -o $@ game.c
clean:
\trm -rf build
"""


class NativeC64Error(ValueError):
    """Original generated game exceeds C64 constraints or lacks rights authority."""


@dataclass(frozen=True, slots=True)
class NativeC64SourceProject:
    game_c: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_c64_cc65_prg_source"
    binary_built: bool = False
    emulator_verified: bool = False
    physical_hardware_verified: bool = False


def compile_native_c64(
    world: PlayableWorld, source: HomebrewSource, *, authorized: bool,
) -> NativeC64SourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("C64 native source requires original homebrew authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise NativeC64Error("typed original world and rights evidence required")
    if world.intent.project_id != source.project_id:
        raise NativeC64Error("source and world project identity mismatch")
    if world.intent.width > _MAX_W or world.intent.height > _MAX_H:
        raise NativeC64Error("generated game exceeds C64 40x25 screen envelope")
    blueprint = compile_port(PortRequest((source,), "commodore_64", PortMode.REVERSE_CONSTRAINED))
    replay = demonstrate_solvable(world, authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise NativeC64Error("no safe original-world victory trace")
    maps = []
    for stage in world.levels:
        flat = [_TILES[cell] for row in stage.rows for cell in row]
        if len(flat) != world.intent.width * world.intent.height:
            raise NativeC64Error("invalid level-map identity")
        maps.append("    {" + ",".join(str(value) for value in flat) + "}")
    replacements = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVELS__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__MAPS__": ",\n".join(maps),
        "__START_X__": ", ".join(str(stage.start[0]) for stage in world.levels),
        "__START_Y__": ", ".join(str(stage.start[1]) for stage in world.levels),
    }
    game_c = _C
    for label, replacement in replacements.items():
        if game_c.count(label) != 1:
            raise NativeC64Error("native C64 source placeholder contract violated")
        game_c = game_c.replace(label, replacement)
    source_manifest = {
        "schema": "skeleton.game_builder.c64_source.v1",
        "project_id": source.project_id,
        "source_platform_id": source.platform_id,
        "target_platform_id": "commodore_64",
        "world_digest": world.digest,
        "reference_safe_replay_digest": replay.digest,
        "rights_evidence_sha256": source.evidence_sha256,
        "blueprint_digest": blueprint.digest,
        "artifact_kind": "c64_basic_loadable_6510_prg_source",
        "gameplay": ["joystick", "collision", "collectibles", "hazards", "health", "levels", "victory"],
        "hardware": ["vic_ii", "cia_joystick_port_2", "sid"],
        "world_dimensions": [world.intent.width, world.intent.height],
        "number_of_levels": len(world.levels),
        "binary_built": False,
        "emulator_verified": False,
        "physical_hardware_verified": False,
        "distribution_licensed": False,
    }
    manifest = json.dumps(source_manifest, sort_keys=True, indent=2) + "\n"
    digest = sha256((game_c + "\0" + _MAKEFILE + "\0" + manifest).encode()).hexdigest()
    return NativeC64SourceProject(game_c, _MAKEFILE, manifest, digest)


def export_native_c64(
    project: NativeC64SourceProject, output: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("C64 native project export requires authorization")
    if not isinstance(project, NativeC64SourceProject):
        raise NativeC64Error("typed C64 project required")
    root = Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True)
    for name, data in (
        ("game.c", project.game_c),
        ("Makefile", project.makefile),
        ("manifest.json", project.manifest_json),
    ):
        with (root / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    return root
