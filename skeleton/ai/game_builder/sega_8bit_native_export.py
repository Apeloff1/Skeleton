"""Original Sega Master System / Game Gear Z80 homebrew source generation.

Two genuinely different display envelopes, VDP palettes and ROM build flags.
The native SDCC/devkitSMS toolchain is external, never downloaded or vendored.
This outputs an original interactive game *source*, not a verified ROM/release.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .game_boy_native_export import _PIXELS
from .playable_simulation import demonstrate_solvable
from .playable_world import PlayableWorld
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port


_TARGETS = {
    "sega_master_system": (31, 21, 0, 2, 0, "sms", "SMSlib.lib"),
    "sega_game_gear": (19, 15, 6, 5, 3, "gg", "SMSlib_GG.lib"),
}
# Original tiles drawn in four-plane SMS VDP format, 8x8x4 = 32 bytes each.
_TILE_IDS = {".": 0, "S": 0, "#": 1, "C": 2, "H": 3, "G": 4}
_BASE = r"""/* Original independently-authored Z80 homebrew: __TARGET__.
 * devkitSMS API is a build dependency, NOT redistributed in this package.
 * No Sega firmware, game ROM, copyrighted sound, or licensed SDK is embedded.
 */
#include "SMSlib.h"

#define WIDTH __WIDTH__
#define HEIGHT __HEIGHT__
#define LEVEL_COUNT __LEVELS__
#define GEMS_PER_LEVEL __GEMS__
#define INITIAL_HEALTH __HEALTH__
#define MAP_SIZE (WIDTH * HEIGHT)
#define LEFT __LEFT__
#define TOP __TOP__
#define HUD_Y __HUD__
#define FLOOR 0
#define WALL 1
#define GEM 2
#define HAZARD 3
#define EXIT 4
#define HERO 5
#define DIGIT_BASE 6
#define HERO_ALT 16
#define BUDDY_IDLE 17
#define BUDDY_BLINK 18
#define BUDDY_HAPPY 19
#define BUDDY_SAD 20
#define BUDDY_CHEER 21

static const unsigned char original_tiles[] = {
__TILES__
};

__MAPS__

static const unsigned char *const authored_maps[] = {
__POINTERS__
};
static const unsigned char authored_spawn_x[] = { __START_X__ };
static const unsigned char authored_spawn_y[] = { __START_Y__ };

static unsigned char board[MAP_SIZE];
static unsigned char level_index, hero_x, hero_y, health, gems_left;
static unsigned char won, lost, move_cooldown;
static unsigned int score;
/* Companion personality, graphics frames and real PSG audio are native. */
static unsigned char companion_clock, companion_mood, companion_drawn, mood_hold;
static unsigned char hero_pose;
static unsigned char bond_collected, bond_rank;
static unsigned char sound_frames, sound_phase;
static const unsigned char bond_goal[7] = { 3, 7, 12, 18, 25, 33, 42 };
__sfr __at (0x7F) PSG_PORT;
#define VRAM_QUEUE_CAPACITY 16
#define VRAM_WRITES_PER_FRAME 3
static unsigned char pending_x[VRAM_QUEUE_CAPACITY], pending_y[VRAM_QUEUE_CAPACITY];
static unsigned char pending_tile[VRAM_QUEUE_CAPACITY], pending_count;

/* Coalesce matching coordinates; a full queue fails closed rather than
 * silently losing screen updates. The logic does not change the game world. */
static void queue_tile(unsigned char x, unsigned char y, unsigned char tile) {
    unsigned char i;
    for (i=0; i<pending_count; ++i) {
        if (pending_x[i]==x && pending_y[i]==y) {
            pending_tile[i]=tile;
            return;
        }
    }
    if (pending_count==VRAM_QUEUE_CAPACITY) {
        lost=1;
        return;
    }
    pending_x[pending_count]=x;
    pending_y[pending_count]=y;
    pending_tile[pending_count]=tile;
    ++pending_count;
}
static void flush_pending(void) {
    unsigned char count, i, remaining;
    count=pending_count<VRAM_WRITES_PER_FRAME ?
        pending_count : VRAM_WRITES_PER_FRAME;
    for (i=0; i<count; ++i)
        SMS_setTileatXY(pending_x[i],pending_y[i],pending_tile[i]);
    remaining=pending_count-count;
    for (i=0; i<remaining; ++i) {
        pending_x[i]=pending_x[i+count];
        pending_y[i]=pending_y[i+count];
        pending_tile[i]=pending_tile[i+count];
    }
    pending_count=remaining;
}

/* Three-channel PSG-compatible hardware; isolated channel 0 for short,
 * self-authored notes. All writes are SDCC Z80 hardware I/O, never samples. */
static void psg_start(unsigned int period, unsigned char frames) {
    PSG_PORT=(unsigned char)(0x80 | (period & 15));
    PSG_PORT=(unsigned char)((period >> 4) & 63);
    PSG_PORT=0x9C; /* attenuated channel-0 volume, not a loud tone */
    sound_frames=frames;
    sound_phase=0;
}
static void psg_tick(void) {
    if (sound_frames==0) return;
    --sound_frames;
    ++sound_phase;
    if ((sound_phase & 3)==0) {
        /* Original two-step arpeggiation, bounded to audio channel zero. */
        PSG_PORT=(unsigned char)(0x80 | ((sound_phase >> 2) & 15));
    }
    if (sound_frames==0) PSG_PORT=0x9F; /* mute channel 0 */
}
/* All tile writes happen with the display off or immediately after VBlank. */
static void write_cell(unsigned char x, unsigned char y) {
    SMS_setTileatXY(LEFT+x, TOP+y, board[(unsigned int)y*WIDTH+x]);
}
static void draw_hud(void) {
    SMS_setTileatXY(LEFT, HUD_Y, GEM);
    SMS_setTileatXY(LEFT+1, HUD_Y, DIGIT_BASE+(gems_left/10));
    SMS_setTileatXY(LEFT+2, HUD_Y, DIGIT_BASE+(gems_left%10));
    SMS_setTileatXY(LEFT+4, HUD_Y, HAZARD);
    SMS_setTileatXY(LEFT+5, HUD_Y, DIGIT_BASE+(health/10));
    SMS_setTileatXY(LEFT+6, HUD_Y, DIGIT_BASE+(health%10));
    SMS_setTileatXY(LEFT+8, HUD_Y, EXIT);
    SMS_setTileatXY(LEFT+9, HUD_Y, DIGIT_BASE+((level_index+1)/10));
    SMS_setTileatXY(LEFT+10, HUD_Y, DIGIT_BASE+((level_index+1)%10));
    SMS_setTileatXY(LEFT+11, HUD_Y, HERO);
    SMS_setTileatXY(LEFT+12, HUD_Y, DIGIT_BASE+bond_rank);
    SMS_setTileatXY(LEFT+14, HUD_Y, DIGIT_BASE+((score/100)%10));
    SMS_setTileatXY(LEFT+15, HUD_Y, DIGIT_BASE+((score/10)%10));
    SMS_setTileatXY(LEFT+16, HUD_Y, DIGIT_BASE+(score%10));
    SMS_setTileatXY(LEFT+18, HUD_Y, companion_mood);
    companion_drawn=companion_mood;
}
/* Friendly companion progression is cosmetic: never changes world collision,
 * source game health, release rights or deterministic collectible scoring. */
static void grant_companion_bond(void) {
    if (bond_collected < 48) ++bond_collected;
    if (bond_rank < 7 && bond_collected >= bond_goal[bond_rank]) {
        ++bond_rank;
        companion_mood=BUDDY_CHEER;
        mood_hold=90;
        psg_start(240, 22);
        queue_tile(LEFT+12,HUD_Y,DIGIT_BASE+bond_rank);
    }
}
static void queue_hud(unsigned char tile) {
    if (tile==GEM) {
        queue_tile(LEFT+1,HUD_Y,DIGIT_BASE+(gems_left/10));
        queue_tile(LEFT+2,HUD_Y,DIGIT_BASE+(gems_left%10));
    } else if (tile==HAZARD) {
        queue_tile(LEFT+5,HUD_Y,DIGIT_BASE+(health/10));
        queue_tile(LEFT+6,HUD_Y,DIGIT_BASE+(health%10));
    } else if (tile==EXIT) {
        queue_tile(LEFT+9,HUD_Y,DIGIT_BASE+((level_index+1)/10));
        queue_tile(LEFT+10,HUD_Y,DIGIT_BASE+((level_index+1)%10));
    }
    if (tile==GEM) {
        queue_tile(LEFT+14,HUD_Y,DIGIT_BASE+((score/100)%10));
        queue_tile(LEFT+15,HUD_Y,DIGIT_BASE+((score/10)%10));
        queue_tile(LEFT+16,HUD_Y,DIGIT_BASE+(score%10));
    }
}
static void draw_hero(void) {
    SMS_setTileatXY(LEFT+hero_x, TOP+hero_y, HERO);
}
/* Render a second independently authored sprite. This is a cosmetic familiar,
 * not a gameplay actor: it never enters board[] or changes physics/replay.
 * Sprite animation uses the VDP sprite attribute table once each VBlank. */
static void render_following_sprite(void) {
    unsigned int x=(unsigned int)(LEFT+hero_x)*8U+6U;
    unsigned int y=(unsigned int)(TOP+hero_y)*8U;
    SMS_initSprites();
    if (y>=13U && x<=247U) {
        y-=((companion_clock & 16) ? 10U : 12U);
        SMS_addSprite((unsigned char)x,(unsigned char)y,companion_mood);
    }
    SMS_copySpritestoSAT();
}
static void animate_companion(void) {
    unsigned char pose;
    ++companion_clock;
    if (mood_hold) {
        --mood_hold;
        pose=companion_mood;
    } else {
        pose=((companion_clock & 63)==0) ? BUDDY_BLINK : BUDDY_IDLE;
        companion_mood=pose;
    }
    if (pose!=companion_drawn && pending_count==0) {
        queue_tile(LEFT+18,HUD_Y,pose);
        companion_drawn=pose;
    }
    if (pending_count==0 && (companion_clock & 31)==0) {
        hero_pose=(hero_pose==HERO) ? HERO_ALT : HERO;
        queue_tile(LEFT+hero_x,TOP+hero_y,hero_pose);
    }
}
static void load_level(void) {
    unsigned int i;
    unsigned char x, y;
    SMS_displayOff();
    pending_count=0; /* old-stage writes cannot leak into the new level */
    companion_mood=BUDDY_CHEER;
    mood_hold=60;
    companion_drawn=BUDDY_IDLE;
    hero_pose=HERO;
    gems_left = GEMS_PER_LEVEL;
    hero_x = authored_spawn_x[level_index];
    hero_y = authored_spawn_y[level_index];
    for (i=0; i<MAP_SIZE; ++i)
        board[i] = authored_maps[level_index][i];
    for (y=0; y<HEIGHT; ++y)
        for (x=0; x<WIDTH; ++x)
            write_cell(x, y);
    draw_hero();
    draw_hud();
    SMS_displayOn();
}
static void end_game(unsigned char victory) {
    if (victory) won=1; else lost=1;
    companion_mood=victory ? BUDDY_CHEER : BUDDY_SAD;
    mood_hold=180;
    psg_start(victory ? 230 : 880, 32);
#ifdef TARGET_GG
    GG_setBGPaletteColor(3, victory ? 0x0F0 : 0x00F);
#else
    SMS_setBGPaletteColor(3, victory ? RGB(0,3,0) : RGB(3,0,0));
#endif
}
static void advance(int dx, int dy) {
    int nx=(int)hero_x+dx, ny=(int)hero_y+dy;
    unsigned int position;
    unsigned char tile;
    if (nx<0 || ny<0 || nx>=WIDTH || ny>=HEIGHT) return;
    position=(unsigned int)ny*WIDTH+(unsigned int)nx;
    tile=board[position];
    if (tile==WALL || (tile==EXIT && gems_left!=0)) return;

    queue_tile(LEFT+hero_x,TOP+hero_y,board[(unsigned int)hero_y*WIDTH+hero_x]);
    hero_x=(unsigned char)nx;
    hero_y=(unsigned char)ny;
    if (tile==GEM) {
        board[position]=FLOOR;
        --gems_left;
        score+=10;
        companion_mood=BUDDY_HAPPY;
        mood_hold=45;
        psg_start(300, 12);
        grant_companion_bond();
    } else if (tile==HAZARD) {
        companion_mood=BUDDY_SAD;
        mood_hold=45;
        psg_start(700, 18);
        if (health!=0) --health;
        if (health==0) end_game(0);
    } else if (tile==EXIT) {
        ++level_index;
        if (level_index==LEVEL_COUNT) {
            end_game(1);
        } else {
            psg_start(380, 20);
            load_level();
            return;
        }
    }
    hero_pose=HERO;
    queue_tile(LEFT+hero_x,TOP+hero_y,HERO);
    queue_hud(tile);
}
void main(void) {
    unsigned int keys;
    SMS_displayOff();
    SMS_loadTiles(original_tiles, 0, sizeof(original_tiles));
    SMS_useFirstHalfTilesforSprites(1);
#ifdef TARGET_GG
    GG_setBGPaletteColor(0, 0x000);
    GG_setBGPaletteColor(1, 0xD94);
    GG_setBGPaletteColor(2, 0x8DC);
    GG_setBGPaletteColor(3, 0xFFF);
    GG_setSpritePaletteColor(0, 0x000);
    GG_setSpritePaletteColor(1, 0xD94);
    GG_setSpritePaletteColor(2, 0x8DC);
    GG_setSpritePaletteColor(3, 0xFFF);
#else
    SMS_setBGPaletteColor(0, RGB(0,0,0));
    SMS_setBGPaletteColor(1, RGB(1,2,3));
    SMS_setBGPaletteColor(2, RGB(0,3,2));
    SMS_setBGPaletteColor(3, RGB(3,3,3));
    SMS_setSpritePaletteColor(0, RGB(0,0,0));
    SMS_setSpritePaletteColor(1, RGB(1,2,3));
    SMS_setSpritePaletteColor(2, RGB(0,3,2));
    SMS_setSpritePaletteColor(3, RGB(3,3,3));
#endif
    level_index=0;
    health=INITIAL_HEALTH;
    score=0;
    won=lost=move_cooldown=0;
    companion_clock=0;
    hero_pose=HERO;
    bond_rank=bond_collected=0;
    companion_mood=BUDDY_IDLE;
    sound_frames=0;
    PSG_PORT=0x9F;
    load_level();
    for (;;) {
        SMS_waitForVBlank();
        flush_pending();
        psg_tick();
        animate_companion();
        render_following_sprite();
        if (won || lost || pending_count) continue;
        if (move_cooldown) { --move_cooldown; continue; }
        keys=SMS_getKeysStatus();
        if (keys & PORT_A_KEY_UP) {
            advance(0,-1);
        } else if (keys & PORT_A_KEY_DOWN) {
            advance(0,1);
        } else if (keys & PORT_A_KEY_LEFT) {
            advance(-1,0);
        } else if (keys & PORT_A_KEY_RIGHT) {
            advance(1,0);
        } else {
            continue;
        }
        move_cooldown=7;
    }
}
/* Standard console compatibility header, not a trademark license claim. */
SMS_EMBED_SEGA_ROM_HEADER(0,0);
"""

_MAKE = """# Toolchain must be provided legally by the builder; nothing is vendored.
SDCC ?= sdcc
MAKESMS ?= makesms
SMSLIB_DIR ?= .
SMSLIB_INC ?= $(SMSLIB_DIR)/src
CRT0_SMS ?= crt0_sms.rel
LIBRARY := __LIBRARY__
TARGET_FLAG := __FLAG__
ROM := skeleton-original.__EXT__
.PHONY: all clean
all: build/$(ROM)
build/game.rel: game.c
\tmkdir -p build
\t$(SDCC) -c -mz80 $(TARGET_FLAG) -I$(SMSLIB_INC) -o $@ $<
build/game.ihx: build/game.rel
\t$(SDCC) -o $@ -mz80 --no-std-crt0 --data-loc 0xC000 $(CRT0_SMS) $< $(SMSLIB_DIR)/$(LIBRARY)
build/$(ROM): build/game.ihx
\t$(MAKESMS) $< $@
clean:
\trm -rf build
"""


class Sega8BitNativeError(ValueError):
    """The requested original game exceeds a native Z80 console envelope."""


@dataclass(frozen=True, slots=True)
class Sega8BitSourceProject:
    game_c: str
    makefile: str
    manifest_json: str
    content_digest: str
    target_platform_id: str
    artifact_kind: str = "native_sega_8bit_sdcc_vdp_original_game_source"
    cartridge_compiled: bool = False
    emulator_playthrough_verified: bool = False
    physical_hardware_verified: bool = False

    def __post_init__(self) -> None:
        if self.target_platform_id not in _TARGETS:
            raise Sega8BitNativeError("unrecognized original Z80 target")
        if (self.cartridge_compiled is not False
                or self.emulator_playthrough_verified is not False
                or self.physical_hardware_verified is not False):
            raise Sega8BitNativeError("native source cannot self-certify real machine execution")
        digest = sha256((
            self.game_c + "\0" + self.makefile + "\0" + self.manifest_json
        ).encode("utf-8")).hexdigest()
        if digest != self.content_digest:
            raise Sega8BitNativeError("native source bytes changed after generation")
        try:
            manifest = json.loads(self.manifest_json)
        except (ValueError, TypeError) as exc:
            raise Sega8BitNativeError("invalid original game manifest") from exc
        if (not isinstance(manifest, dict)
                or manifest.get("schema") != "skeleton.game_builder.native_sega8_source.v1"
                or manifest.get("platform") != self.target_platform_id
                or not isinstance(manifest.get("world_digest"), str)):
            raise Sega8BitNativeError("native game manifest identity mismatch")
        if any(manifest.get(flag) is not False for flag in (
            "binary_compiled", "emulator_playthrough_verified",
            "physical_hardware_verified", "distribution_licensed",
            "release_approved", "third_party_game_or_firmware_redistributed",
        )):
            raise Sega8BitNativeError("unreviewed cartridge cannot claim release or execution")


def _tiles() -> str:
    """Original 2-bit graphics -> genuine four-plane SMS VDP tile bytes."""
    chars: list[tuple[str, ...]] = list(_PIXELS)
    # Independently drawn original 3x5 numeral glyphs, not font ROM content.
    numerals = (
        ("111","101","101","101","111"),
        ("010","110","010","010","111"),
        ("111","001","111","100","111"),
        ("111","001","111","001","111"),
        ("101","101","111","001","001"),
        ("111","100","111","001","111"),
        ("111","100","111","101","111"),
        ("111","001","001","001","001"),
        ("111","101","111","101","111"),
        ("111","101","111","001","111"),
    )
    for num in numerals:
        chars.append(tuple(
            "00" + (num[y-1].replace("1", "3") if 1 <= y <= 5 else "000") + "000"
            for y in range(8)
        ))
    # Six native animation phases: sparkle pose, curious, blink, joy, injury,
    # and celebration. No third-party sprites, screenshots or sampled art.
    authored_poses = (
        ("00333300","03111130","31133113","31311313",
         "31133113","03111130","30300303","03033030"),
        ("00111100","01333310","13333331","33033033",
         "33033033","33000033","03333330","00333300"),
        ("00111100","01333310","13333331","33000033",
         "33333333","33000033","03333330","00333300"),
        ("00111100","01333310","13333331","33033033",
         "33000033","33100133","03111130","00333300"),
        ("00111100","01333310","13333331","33033033",
         "33000033","33311333","03111130","00333300"),
        ("03033030","30333303","13333331","33033033",
         "33000033","33111133","03333330","30300303"),
    )
    chars.extend(authored_poses)
    result: list[str] = []
    for tile in chars:
        for row in tile:
            if len(row) != 8 or any(p not in "0123" for p in row):
                raise Sega8BitNativeError("source tile pixels invalid")
            for plane in range(4):
                value = sum(((int(p) >> plane) & 1) << (7-x) for x,p in enumerate(row))
                result.append(f"0x{value:02x}")
    if len(result) != 22 * 32:
        raise Sega8BitNativeError("console VDP tile length invalid")
    return ",\n".join(
        "    " + ", ".join(result[i:i+16])
        for i in range(0,len(result),16)
    )


def compile_native_sega_8bit(
    world: PlayableWorld, source: HomebrewSource, target: str, *, authorized: bool,
) -> Sega8BitSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Sega original homebrew generation requires explicit authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise Sega8BitNativeError("typed authored game and homebrew source required")
    if target not in _TARGETS:
        raise Sega8BitNativeError("unsupported native Z80 console target")
    if world.intent.project_id != source.project_id:
        raise Sega8BitNativeError("authored world and rights source identity mismatch")
    width, height, left, top, hud, ext, library = _TARGETS[target]
    if world.intent.width > width or world.intent.height > height:
        raise Sega8BitNativeError("game exceeds destination screen tile budget")
    if world.intent.starting_health > 10 or len(world.levels) > 8:
        raise Sega8BitNativeError("game exceeds Z80 runtime state budget")
    plan = compile_port(PortRequest((source,),target,PortMode.REVERSE_CONSTRAINED))
    replay = demonstrate_solvable(world,authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise Sega8BitNativeError("original gameplay is not replay-proven")
    maps = []
    for level in world.levels:
        mapped = [_TILE_IDS[c] for row in level.rows for c in row]
        maps.append(
            f"static const unsigned char stage_{level.index}[MAP_SIZE] = {{\n"
            + "\n".join(
                "    " + ", ".join(str(v) for v in mapped[i:i+24]) + ","
                for i in range(0,len(mapped),24)
            )
            + "\n};"
        )
    substitutions = {
        "__TARGET__":target,"__WIDTH__":str(world.intent.width),
        "__HEIGHT__":str(world.intent.height),"__LEVELS__":str(len(world.levels)),
        "__GEMS__":str(world.intent.collectibles_per_level),
        "__HEALTH__":str(world.intent.starting_health),
        "__LEFT__":str(left),"__TOP__":str(top),"__HUD__":str(hud),
        "__TILES__":_tiles(),"__MAPS__":"\n\n".join(maps),
        "__POINTERS__":", ".join(f"stage_{level.index}" for level in world.levels),
        "__START_X__":", ".join(str(l.start[0]) for l in world.levels),
        "__START_Y__":", ".join(str(l.start[1]) for l in world.levels),
    }
    code = _BASE
    for marker, val in substitutions.items():
        if code.count(marker) != 1:
            raise Sega8BitNativeError("native C generation marker violated")
        code = code.replace(marker,val)
    makefile = (_MAKE.replace("__LIBRARY__",library)
                .replace("__EXT__",ext)
                .replace("__FLAG__","-D TARGET_GG" if ext=="gg" else ""))
    manifest = {
        "schema":"skeleton.game_builder.native_sega8_source.v1",
        "platform":target,"project_id":source.project_id,
        "source_platform":source.platform_id,
        "source_rights_evidence_sha256":source.evidence_sha256,
        "world_digest":world.digest,
        "reference_safe_replay_digest":replay.digest,
        "reference_safe_moves":sum(len(l.safe_solution) for l in world.levels),
        "port_blueprint_digest":plan.digest,
        "target_rom_suffix":ext,
        "levels":len(world.levels),"width":world.intent.width,
        "height":world.intent.height,
        "title":world.intent.title,
        "native_psg_reactive_audio":True,
        "native_animated_companion":True,
        "original_companion_pose_count":5,
        "original_hero_pose_count":2,
        "companion_bond_ranks":8,
        "companion_progression_changes_core_gameplay":False,
        "animation_vram_writes_per_frame":3,
        "hardware_sprite_claim":False,
        "native_sprite_familiar_source_present":True,
        "native_sprite_collision_authority":False,
        "historical_sdk_downloaded":False,
        "third_party_game_or_firmware_redistributed":False,
        "binary_compiled":False,
        "emulator_playthrough_verified":False,
        "physical_hardware_verified":False,
        "distribution_licensed":False,
        "release_approved":False,
        "toolchain_license_review_required":True,
    }
    manifest_json=json.dumps(manifest,indent=2,sort_keys=True)+"\n"
    digest=sha256((code+"\0"+makefile+"\0"+manifest_json).encode("utf-8")).hexdigest()
    return Sega8BitSourceProject(code,makefile,manifest_json,digest,target)


def export_native_sega_8bit(
    project: Sega8BitSourceProject, destination: str | Path, *, authorized: bool,
) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("Sega homebrew source export requires authorization")
    if not isinstance(project,Sega8BitSourceProject):
        raise Sega8BitNativeError("typed original hardware source required")
    if project.target_platform_id not in _TARGETS:
        raise Sega8BitNativeError("native hardware project target invalid")
    digest=sha256((project.game_c+"\0"+project.makefile+"\0"+project.manifest_json).encode()).hexdigest()
    if digest!=project.content_digest:
        raise Sega8BitNativeError("native hardware project bytes changed")
    path=Path(destination)
    if path.exists() or path.is_symlink():
        raise FileExistsError(str(path))
    path.mkdir(parents=True,exist_ok=False)
    for name,body in (
        ("game.c",project.game_c),
        ("Makefile",project.makefile),
        ("manifest.json",project.manifest_json),
    ):
        with (path/name).open("x",encoding="utf-8",newline="\n") as out:
            out.write(body)
    return path
