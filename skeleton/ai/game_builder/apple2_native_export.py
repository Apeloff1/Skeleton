"""Original Apple II+/IIe 6502 game source: real keyboard, 40x24, speaker.

Target is cc65's genuine Apple II AppleSingle BLOAD-compatible binary output,
not a C64 or Atari executable renamed for Apple. The output intentionally does
not bundle Apple system ROM, DOS 3.3 disk images, software samples or firmware.
The stock cc65 apple2 target requires a compatible runtime/Language Card;
unexpanded first-generation Apple II hardware is not claimed to be supported.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_world import PlayableWorld
from .playable_simulation import demonstrate_solvable
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

MAX_WIDTH = 37
MAX_HEIGHT = 21
MAX_LEVELS = 8
_MAP_TILE = {".":0,"S":0,"#":1,"C":2,"H":3,"G":4}

_C = r"""/* Original Apple II+/IIe 6502 adventure. No third-party code or ROMs. */
#include <conio.h>
typedef unsigned char u8;
typedef unsigned int u16;

#define WIDTH __WIDTH__
#define HEIGHT __HEIGHT__
#define LEVELS __LEVELS__
#define GEMS __GEMS__
#define FIRST_HEALTH __HEALTH__
#define CELLS (WIDTH * HEIGHT)
#define SPEAKER (*(volatile u8*)0xC030) /* Genuine Apple II speaker toggle. */
#define T_FLOOR 0
#define T_WALL 1
#define T_GEM 2
#define T_HAZARD 3
#define T_EXIT 4

static const u8 authored_maps[LEVELS][CELLS] = {
__MAPS__
};
static const u8 spawn_x[LEVELS] = { __START_X__ };
static const u8 spawn_y[LEVELS] = { __START_Y__ };
static const char glyph[5] = { '.', '#', '*', '!', '>' };
static u8 writable_map[CELLS];
static u8 level, player_x, player_y, gems_left, health, won, lost;
static u16 score;

static u16 offset(u8 px, u8 py) { return (u16)py * WIDTH + px; }

/* Apple II $C030 toggles the built-in piezo speaker on every access. */
static void sound(u8 note) {
    volatile u8 unused;
    u8 n;
    for (n = 0; n < 12; ++n) {
        u8 delay;
        unused = SPEAKER;
        for (delay=0; delay<note; ++delay) { }
    }
    (void)unused;
}

static void digit(u8 value) {
    cputc((char)('0' + value % 10));
}

static void hud(void) {
    gotoxy(0, 0);
    cputs("ORIGINAL APPLE II ADVENTURE LEVEL ");
    digit((u8)(level + 1));
    cputs(" ");
    gotoxy(0, 22);
    cputs("GEMS:"); digit(gems_left);
    cputs(" HP:"); digit(health);
    cputs(" SCORE:");
    digit((u8)(score/1000 % 10));
    digit((u8)(score/100 % 10));
    digit((u8)(score/10 % 10));
    digit((u8)(score % 10));
    cputs("  ");
    gotoxy(0, 23);
    cputs("IJKL OR WASD MOVEMENT. ESC TO QUIT.  ");
}

static void draw_tile(u8 px, u8 py) {
    gotoxy((u8)(px + 1), (u8)(py + 1));
    cputc(glyph[writable_map[offset(px,py)]]);
}

static void draw_player(void) {
    gotoxy((u8)(player_x + 1), (u8)(player_y + 1));
    cputc('@');
}

static void load_level(void) {
    u16 n;
    gems_left = GEMS;
    player_x = spawn_x[level];
    player_y = spawn_y[level];
    clrscr();
    for (n = 0; n < CELLS; ++n) writable_map[n] = authored_maps[level][n];
    for (n = 0; n < CELLS; ++n)
        draw_tile((u8)(n % WIDTH), (u8)(n / WIDTH));
    hud();
    draw_player();
}

static void move(u8 nx, u8 ny) {
    u16 pos;
    u8 tile;
    if (nx >= WIDTH || ny >= HEIGHT) return;
    pos = offset(nx, ny);
    tile = writable_map[pos];
    if (tile == T_WALL) return;
    draw_tile(player_x,player_y);
    player_x = nx;
    player_y = ny;
    if (tile == T_GEM) {
        writable_map[pos] = T_FLOOR;
        --gems_left;
        score = (u16)(score + 10);
        sound(15);
    } else if (tile == T_HAZARD) {
        if (health) --health;
        sound(55);
        if (health == 0) lost = 1;
    } else if (tile == T_EXIT && gems_left == 0) {
        score = (u16)(score + 100);
        if ((u8)(level + 1) == LEVELS) {
            won = 1;
        } else {
            ++level;
            load_level();
            return;
        }
    }
    draw_player();
    hud();
}

int main(void) {
    char key;
    level = 0;
    health = FIRST_HEALTH;
    won = 0;
    lost = 0;
    score = 0;
    load_level();
    for (;;) {
        key = cgetc();  /* Actual Apple II keyboard, no host input service. */
        if (key == 27) break;
        if (won || lost) break;
        switch (key) {
        case 'I': case 'i': case 'W': case 'w':
            if (player_y) move(player_x, (u8)(player_y-1)); break;
        case 'K': case 'k': case 'S': case 's':
            move(player_x, (u8)(player_y+1)); break;
        case 'J': case 'j': case 'A': case 'a':
            if (player_x) move((u8)(player_x-1), player_y); break;
        case 'L': case 'l': case 'D': case 'd':
            move((u8)(player_x+1), player_y); break;
        default: break;
        }
        if (won || lost) {
            gotoxy(0, 21);
            if (won) cputs("VICTORY! ORIGINAL GAME COMPLETED.    ");
            else cputs("GAME OVER. PRESS ANY KEY.            ");
            sound((u8)(won ? 9 : 65));
        }
    }
    return 0;
}
"""
_MAKEFILE = """CL65 ?= cl65
.PHONY: all clean
all: build/skeleton-original.as
build/skeleton-original.as: game.c
\tmkdir -p build
\t$(CL65) -t apple2 -O -o $@ game.c
clean:
\trm -rf build
"""


class Apple2NativeError(ValueError):
    """Native original Apple II source violates video, rights or proof budget."""


@dataclass(frozen=True, slots=True)
class Apple2SourceProject:
    game_c: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_apple2_cc65_6502_applesingle_source"
    binary_compiled: bool = False
    emulator_verified: bool = False
    original_hardware_verified: bool = False


def compile_native_apple2(
    world: PlayableWorld, rights: HomebrewSource, *, authorized: bool,
) -> Apple2SourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Apple II requires explicit original-homebrew authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(rights, HomebrewSource):
        raise Apple2NativeError("typed original world and homebrew rights evidence required")
    if world.intent.project_id != rights.project_id:
        raise Apple2NativeError("Apple II original world and authorship project mismatch")
    if (world.intent.width > MAX_WIDTH or world.intent.height > MAX_HEIGHT
            or len(world.levels) > MAX_LEVELS):
        raise Apple2NativeError("Apple II 40x24 original text screen or 6502 budget exceeded")
    if world.intent.collectibles_per_level > 9 or world.intent.starting_health > 9:
        raise Apple2NativeError("Apple II original text HUD counter width exceeded")
    replay = demonstrate_solvable(world, authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise Apple2NativeError("original Apple II world lacks safe-winning replay")
    plan = compile_port(PortRequest((rights,), "apple_ii", PortMode.REVERSE_CONSTRAINED))
    rows = []
    for stage in world.levels:
        values = [_MAP_TILE[char] for line in stage.rows for char in line]
        if len(values) != world.intent.width * world.intent.height:
            raise Apple2NativeError("corrupted authored Apple II world cells")
        rows.append("    {" + ", ".join(str(v) for v in values) + "}")
    tokens = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVELS__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__MAPS__": ",\n".join(rows),
        "__START_X__": ", ".join(str(stage.start[0]) for stage in world.levels),
        "__START_Y__": ", ".join(str(stage.start[1]) for stage in world.levels),
    }
    code = _C
    for token, value in tokens.items():
        if code.count(token) != 1:
            raise Apple2NativeError("native Apple II assembler-source substitution conflict")
        code = code.replace(token, value)
    manifest = json.dumps({
        "schema": "skeleton.game_builder.native_apple2_source.v1",
        "platform": "apple_ii",
        "runtime_assumption": "Apple_II_plus_or_IIe_with_language_card",
        "format": "apple2_applesingle_bload_6502",
        "project_id":rights.project_id,
        "source_platform":rights.platform_id,
        "world_digest":world.digest,
        "reference_replay_digest":replay.digest,
        "rights_evidence_sha256":rights.evidence_sha256,
        "port_blueprint_digest":plan.digest,
        "levels":len(world.levels),
        "width":world.intent.width,
        "height":world.intent.height,
        "authored_source_only":True,
        "binary_compiled":False,
        "emulator_playthrough_verified":False,
        "original_hardware_verified":False,
        "redistribution_licensed":False,
        "third_party_rom_included":False,
    },sort_keys=True,indent=2)+"\n"
    digest = sha256((code+"\0"+_MAKEFILE+"\0"+manifest).encode()).hexdigest()
    return Apple2SourceProject(code,_MAKEFILE,manifest,digest)


def export_native_apple2(project:Apple2SourceProject,output:str|Path,*,authorized:bool)->Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Apple II export requires explicit authorization")
    if not isinstance(project,Apple2SourceProject):
        raise Apple2NativeError("typed original Apple II source project required")
    root=Path(output)
    if root.exists() or root.is_symlink():
        raise FileExistsError(str(root))
    root.mkdir(parents=True,exist_ok=False)
    for name,data in (("game.c",project.game_c),("Makefile",project.makefile),
                      ("manifest.json",project.manifest_json)):
        with (root/name).open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(data)
    return root
