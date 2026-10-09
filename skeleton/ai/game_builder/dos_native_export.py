"""Generate a genuine DOS 8086 .COM maze game from an ORIGINAL solved world.

Target: IBM PC-compatible real-mode DOS using BIOS keyboard/video initialization
and text-mode video memory at B800:0000. Nothing from DOS, MS-DOS, IBM,
commercial games, firmware images or third-party art is redistributed.
Compilation, emulation and legal release are independent gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .playable_world import PlayableWorld
from .playable_simulation import demonstrate_solvable
from .port_planner import HomebrewSource, PortMode, PortRequest, compile_port

_MAX_WIDTH = 39
_MAX_HEIGHT = 23
_MAX_LEVELS = 8
_TILE_IDS = {".": 0, "S": 0, "#": 1, "C": 2, "H": 3, "G": 4}

_ASM = r"""; Original Skeleton authored 8086 game, IBM PC DOS .COM format.
; No commercial artwork, ROM dump, BIOS binary or proprietary SDK bundled.
bits 16
cpu 8086
org 100h

%define WIDTH __WIDTH__
%define HEIGHT __HEIGHT__
%define CELLS (WIDTH * HEIGHT)
%define LEVELS __LEVELS__
%define GEMS __GEMS__
%define START_HEALTH __HEALTH__
%define TILE_WALL 1
%define TILE_GEM 2
%define TILE_HAZARD 3
%define TILE_GOAL 4

Start:
    push cs
    pop ds
    mov ax, 0003h
    int 10h
    mov ax, 0B800h
    mov es, ax
    xor ax, ax
    mov [level], al
    mov [won], al
    mov [lost], al
    mov [score], ax
    mov al, START_HEALTH
    mov [health], al
    call LoadLevel
    call Render

GameLoop:
    xor ah, ah
    int 16h
    cmp ah, 01h             ; Escape exits without modifying files.
    jne .process_key
    jmp ExitGame
.process_key:
    mov bl, [player_x]
    mov [candidate_x], bl
    mov bl, [player_y]
    mov [candidate_y], bl
    cmp ah, 48h             ; Real BIOS arrow-key scan codes.
    je .up
    cmp ah, 50h
    je .down
    cmp ah, 4Bh
    je .left
    cmp ah, 4Dh
    je .right
    jmp GameLoop
.up:
    dec byte [candidate_y]
    jmp .move
.down:
    inc byte [candidate_y]
    jmp .move
.left:
    dec byte [candidate_x]
    jmp .move
.right:
    inc byte [candidate_x]
.move:
    call TryMove
    call Render
    cmp byte [won], 0
    jne Victory
    cmp byte [lost], 0
    jne Defeat
    jmp GameLoop

Victory:
    mov si, win_text
    call PrintStatus
    jmp EndScreen
Defeat:
    mov si, lost_text
    call PrintStatus
EndScreen:
    xor ah, ah
    int 16h
ExitGame:
    mov ax, 4C00h
    int 21h

; ES points to real IBM CGA/EGA/VGA text video memory.
Render:
    xor di, di
    mov ax, 0720h
    mov cx, 2000
    rep stosw
    mov si, map_ram
    mov di, 322            ; Row two, column one (zero-based).
    mov bp, HEIGHT
.row:
    mov cx, WIDTH
.cell:
    lodsb
    mov bx, tile_glyphs
    xlatb
    mov ah, 0Fh
    stosw
    loop .cell
    add di, (160 - WIDTH * 2)
    dec bp
    jnz .row
    ; Draw player as a separate overlay; retain the underlying authored tile.
    xor ax, ax
    mov al, [player_y]
    add ax, 2
    mov bx, 160
    mul bx
    mov di, ax
    xor ax, ax
    mov al, [player_x]
    inc ax
    shl ax, 1
    add di, ax
    mov ax, 1F40h          ; Bright white @ on blue.
    stosw
    mov si, hud_title
    xor di, di
.hud:
    lodsb
    or al, al
    jz .numbers
    mov ah, 0Fh
    stosw
    jmp .hud
.numbers:
    mov al, [level]
    inc al
    add al, 30h
    mov [es:52], al        ; LEVEL:0 value at character 26.
    mov al, [gems_left]
    add al, 30h
    mov [es:68], al        ; GEMS:0 value at character 34.
    mov al, [health]
    add al, 30h
    mov [es:80], al        ; HP:0 value at character 40.
    mov ax, [score]
    mov bx, 1000
    mov di, 98            ; SCORE:0000 first digit, character 49.
    mov cx, 4
.digits:
    xor dx, dx
    div bx
    add al, 30h
    mov [es:di], al
    add di, 2
    mov ax, dx
    push ax
    mov ax, bx
    xor dx, dx
    mov bp, 10
    div bp
    mov bx, ax
    pop ax
    loop .digits
    ret

PrintStatus:
    mov di, 160           ; Second text row: no interference with the maze.
.next:
    lodsb
    or al, al
    jz .done
    mov ah, 1Eh
    stosw
    jmp .next
.done:
    ret

LoadLevel:
    mov al, GEMS
    mov [gems_left], al
    xor bx, bx
    mov bl, [level]
    mov al, [start_x + bx]
    mov [player_x], al
    mov al, [start_y + bx]
    mov [player_y], al
    shl bx, 1
    mov si, [level_ptrs + bx]
    mov di, map_ram
    mov cx, CELLS
.copy:
    lodsb
    mov [di], al           ; DS:DI (not ES:DI): writable private game map.
    inc di
    loop .copy
    ret

TryMove:
    mov al, [candidate_x]
    cmp al, WIDTH
    jb .x_inside
    ret
.x_inside:
    mov al, [candidate_y]
    cmp al, HEIGHT
    jb .y_inside
    ret
.y_inside:
    xor ax, ax
    mov al, [candidate_y]
    mov bx, WIDTH
    mul bx
    xor bx, bx
    mov bl, [candidate_x]
    add ax, bx
    mov si, ax
    mov dl, [map_ram + si]
    cmp dl, TILE_WALL
    je .blocked
    mov al, [candidate_x]
    mov [player_x], al
    mov al, [candidate_y]
    mov [player_y], al
    cmp dl, TILE_GEM
    jne .hazard
    mov byte [map_ram + si], 0
    dec byte [gems_left]
    add word [score], 10
    ret
.hazard:
    cmp dl, TILE_HAZARD
    jne .goal
    dec byte [health]
    jnz .blocked
    mov byte [lost], 1
    ret
.goal:
    cmp dl, TILE_GOAL
    jne .blocked
    cmp byte [gems_left], 0
    jne .blocked
    add word [score], 100
    inc byte [level]
    mov al, [level]
    cmp al, LEVELS
    jb .next_level
    dec byte [level]       ; Final level remains a valid RAM state.
    mov byte [won], 1
    ret
.next_level:
    call LoadLevel
.blocked:
    ret

hud_title: db "ORIGINAL HOMEBREW   LEVEL:0  GEMS:0  HP:0  SCORE:0000",0
win_text: db "VICTORY - ALL ORIGINAL LEVELS COMPLETED. PRESS ANY KEY.",0
lost_text: db "GAME OVER - PRESS ANY KEY TO EXIT.",0
tile_glyphs: db ".", 0B2h, "*", "!", "E"
level_ptrs:
__POINTERS__
start_x: db __START_X__
start_y: db __START_Y__
__MAP_DATA__

level: db 0
player_x: db 0
player_y: db 0
candidate_x: db 0
candidate_y: db 0
gems_left: db 0
health: db 0
score: dw 0
won: db 0
lost: db 0
map_ram: times CELLS db 0
original_game_signature: db "SKELDOS1"
; Original engine symbols, self-locating offsets for independent 8086 gameplay QA.
; The metadata is DATA ONLY; the game does not read or trust this table.
state_trace_signature: db "SKELDOSSTATE"
state_trace_offsets: dw level, player_x, player_y, health
                     dw score, gems_left, won, lost
"""
_MAKEFILE = """NASM ?= nasm
.PHONY: all clean
all: build/skeleton-original.com
build/skeleton-original.com: game.asm
\tmkdir -p build
\t$(NASM) -f bin -o $@ $<
clean:
\trm -rf build
"""


class NativeDOSError(ValueError):
    """Unsafe rights, unsupported 8086 authoring map or invalid source state."""


@dataclass(frozen=True, slots=True)
class NativeDOSSourceProject:
    game_asm: str
    makefile: str
    manifest_json: str
    content_digest: str
    artifact_kind: str = "native_ibm_pc_dos_8086_com_source"
    executable_built: bool = False
    dos_emulator_verified: bool = False
    hardware_verified: bool = False


def compile_native_dos(
    world: PlayableWorld, source: HomebrewSource, *, authorized: bool,
) -> NativeDOSSourceProject:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("DOS original source requires explicit authorization")
    if not isinstance(world, PlayableWorld) or not isinstance(source, HomebrewSource):
        raise NativeDOSError("typed original world and rights-bound homebrew source required")
    if source.project_id != world.intent.project_id:
        raise NativeDOSError("world and original-rights project mismatch")
    if (world.intent.width > _MAX_WIDTH or world.intent.height > _MAX_HEIGHT
            or len(world.levels) > _MAX_LEVELS):
        raise NativeDOSError("DOS real-mode text-map or level budget exceeded")
    if world.intent.starting_health > 9 or world.intent.collectibles_per_level > 9:
        raise NativeDOSError("DOS HUD's single-digit gameplay budget exceeded")
    blueprint = compile_port(PortRequest((source,), "dos_vga", PortMode.REVERSE_CONSTRAINED))
    replay = demonstrate_solvable(world, authorized=True)
    if replay.world_digest != world.digest or replay.final_state.status != "won":
        raise NativeDOSError("no deterministic winning reference for original DOS game")
    maps = []
    for level in world.levels:
        tiles = [_TILE_IDS[c] for row in level.rows for c in row]
        if len(tiles) != world.intent.width * world.intent.height:
            raise NativeDOSError("source game-map cells are incomplete")
        maps.append(f"level_map_{level.index}: db " + ", ".join(str(i) for i in tiles))
    replace = {
        "__WIDTH__": str(world.intent.width),
        "__HEIGHT__": str(world.intent.height),
        "__LEVELS__": str(len(world.levels)),
        "__GEMS__": str(world.intent.collectibles_per_level),
        "__HEALTH__": str(world.intent.starting_health),
        "__POINTERS__": "\n".join(f"    dw level_map_{i}" for i in range(len(world.levels))),
        "__START_X__": ", ".join(str(l.start[0]) for l in world.levels),
        "__START_Y__": ", ".join(str(l.start[1]) for l in world.levels),
        "__MAP_DATA__": "\n".join(maps),
    }
    asm = _ASM
    for key, value in replace.items():
        if asm.count(key) != 1:
            raise NativeDOSError("8086 source marker inconsistent")
        asm = asm.replace(key, value)
    manifest = {
        "schema": "skeleton.game_builder.native_dos_com.v1",
        "project_id": source.project_id,
        "rights_evidence_sha256": source.evidence_sha256,
        "source_platform_id": source.platform_id,
        "target_platform_id": "dos_vga",
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "port_blueprint_digest": blueprint.digest,
        "format": "16bit_8086_dos_com_textmode",
        "engine": "original_8086_bios_keyboard_vram_maze",
        "graphics": "IBM_PC_text_mode_3_original_glyphs",
        "levels": len(world.levels),
        "width": world.intent.width,
        "height": world.intent.height,
        "reference_safe_actions": sum(len(l.safe_solution) for l in world.levels),
        "executable_built": False,
        "dos_emulator_verified": False,
        "physical_hardware_verified": False,
        "distribution_licensed": False,
    }
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return NativeDOSSourceProject(
        asm, _MAKEFILE, manifest_json,
        sha256((asm + "\0" + _MAKEFILE + "\0" + manifest_json).encode("utf-8")).hexdigest(),
    )


def export_native_dos(project: NativeDOSSourceProject, output: str | Path, *, authorized: bool) -> Path:
    if type(authorized) is not bool or not authorized:
        raise PermissionError("native DOS source export requires explicit authorization")
    if not isinstance(project, NativeDOSSourceProject):
        raise NativeDOSError("native DOS source project required")
    folder = Path(output)
    if folder.exists() or folder.is_symlink():
        raise FileExistsError(str(folder))
    folder.mkdir(parents=True, exist_ok=False)
    for name, body in (
        ("game.asm", project.game_asm),
        ("Makefile", project.makefile),
        ("manifest.json", project.manifest_json),
    ):
        with (folder / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(body)
    return folder
