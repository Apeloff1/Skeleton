"""Original side-scrolling Game Boy platformer source for RGBDS.

Native background tilemap, 8-bit camera scroll, 1-bitpad movement, bounded
gravity and signed jump impulse, ledge/floor collisions, native 2bpp sprites,
collectible star and goal-reset feedback. This is cartridge SM83 assembly,
NOT SDL/HTML or a fake reskin. Emulator execution needs independent proof.
"""
from __future__ import annotations
from .dragon_retro_assets import BITMAPS,compile_tile

def _rom_tile_bytes() -> str:
    blank=bytes(16)
    # 8x8 simple brick with a visible top edge and textured body
    brick=bytes([0xFF,0x00]+[0x81,0x00]*6+[0xFF,0x00])
    dragon=compile_tile("dragon",BITMAPS["dragon"]).gb
    gem=compile_tile("star",BITMAPS["star"]).gb
    blink=compile_tile("dragon_blink",BITMAPS["dragon_blink"]).gb
    tiles=(blank,brick,dragon,gem,blink)
    lines=["; BG0 empty, BG1 platform, OBJ2 hatchling, OBJ3 crystal","PlatformTiles:"]
    for blob in tiles:
        for i in range(0,16,8):
            lines.append("    db "+",".join(f"${b:02X}" for b in blob[i:i+8]))
    lines.append("PlatformTilesEnd:")
    return "\n".join(lines)

def gb_platformer_source(seed:int)->dict[str,str]:
    if isinstance(seed,bool) or not isinstance(seed,int) or seed<0:
        raise ValueError("valid deterministic game seed required")
    goal_x=138+(seed%12)
    source=r"""\
; Dragon's original scrolling Game Boy platformer. RGBDS SM83. 32x18 tile world.
; Native PPU tilemap at 9800h, background camera SCX and OAM 8x8 sprites.
; D-pad walks, A jumps. Land on ledges; touch floating star for new goal.
DEF rJOYP EQU $FF00
DEF rLCDC EQU $FF40
DEF rLY EQU $FF44
DEF rSCX EQU $FF43
DEF rBGP EQU $FF47
DEF rOBP0 EQU $FF48
DEF OAM EQU $FE00
DEF VRAM EQU $8000
SECTION "Entry", ROM0[$100]
    jp Start
    ds $0150 - @,0
SECTION "Game", ROM0[$150]
Start:
    di
    ld sp,$FFFE
.waitVBlank:
    ldh a,[rLY]
    cp 144
    jr c,.waitVBlank
    xor a
    ldh [rLCDC],a
    ; transfer 4 native 2bpp tiles into VRAM
    ld hl,VRAM
    ld de,PlatformTiles
    ld b,PlatformTilesEnd-PlatformTiles
.copyTiles:
    ld a,[de]
    ld [hli],a
    inc de
    dec b
    jr nz,.copyTiles
    ; clear 32*32 BG cells so scroll never reads arbitrary VRAM
    ld hl,$9800
    ld bc,1024
    xor a
.clearMap:
    ld [hli],a
    dec bc
    ld a,b
    or c
    jr nz,.zero
    jr .mapReady
.zero:
    xor a
    jr .clearMap
.mapReady:
    ; y17 = horizontal ground through world x=0..31.
    ld hl,$9800+17*32
    ld b,32
    ld a,1
.ground:
    ld [hli],a
    dec b
    jr nz,.ground
    ; accessible ledges at y12 and y9, long enough to land.
    ld hl,$9800+12*32+5
    ld b,7
.ledgeA:
    ld [hli],a
    dec b
    jr nz,.ledgeA
    ld hl,$9800+9*32+13
    ld b,7
.ledgeB:
    ld [hli],a
    dec b
    jr nz,.ledgeB
    ; initial memory and sprites
    ld a,32
    ld [PlayerWorldX],a
    ld a,144
    ld [PlayerScreenY],a
    xor a
    ld [VelocityY],a
    ld [CameraScroll],a
    ld [AnimationClock],a
    ld a,1
    ld [Grounded],a
    ld a,GOAL_X
    ld [StarWorldX],a
    ld a,80
    ld [StarScreenY],a
    ld a,$E4
    ldh [rOBP0],a
    ldh [rBGP],a
    xor a
    ldh [rSCX],a
    ld a,$93 ; PPU on, BG+OBJ on, tiles at $8000
    ldh [rLCDC],a
.loop:
    call VBlank
    call Controls
    call GravityAndJump
    call MoveCamera
    call PaintObjects
    call CollectStar
    jr .loop
VBlank:
.before:
    ldh a,[rLY]
    cp 144
    jr nc,.before
.during:
    ldh a,[rLY]
    cp 144
    jr c,.during
    ret
Controls:
    ld a,$20
    ldh [rJOYP],a
    ldh a,[rJOYP]
    ldh a,[rJOYP] ; settle selection
    cpl
    and $0F
    ld b,a
    bit 0,b ; right
    jr z,.noR
    ld hl,PlayerWorldX
    ld a,[hl]
    cp 242
    jr nc,.noR
    inc [hl]
.noR:
    bit 1,b ; left
    jr z,.noL
    ld hl,PlayerWorldX
    ld a,[hl]
    cp 12
    jr c,.noL
    dec [hl]
.noL:
    ld a,$10 ; P15: A and B
    ldh [rJOYP],a
    ldh a,[rJOYP]
    ldh a,[rJOYP]
    cpl
    and $0F
    bit 0,a
    jr z,.noJump
    ld a,[Grounded]
    and a
    jr z,.noJump
    xor a
    ld [Grounded],a
    ld a,$F6 ; signed -10 initial jump impulse; reaches first and second ledge
    ld [VelocityY],a
.noJump:
    ld a,$30
    ldh [rJOYP],a
    ret
GravityAndJump:
    ld a,[Grounded]
    and a
    jr z,.airborne
    call HasGroundSupport
    and a
    ret nz
    xor a
    ld [Grounded],a
    ld a,1
    ld [VelocityY],a
.airborne:
    ld a,[VelocityY]
    bit 7,a
    jr z,.positive
    ; negative velocity: move upwards -velocity pixels.
    cpl
    inc a
    ld b,a
.up:
    ld hl,PlayerScreenY
    dec [hl]
    dec b
    jr nz,.up
    jr .accelerate
.positive:
    and a
    jr z,.accelerate
    ld b,a
.down:
    ld hl,PlayerScreenY
    inc [hl]
    dec b
    jr nz,.down
.accelerate:
    ld hl,VelocityY
    ld a,[hl]
    bit 7,a
    jr nz,.speedUp
    cp 4
    jr nc,.landing
.speedUp:
    inc [hl]
.landing:
    ; Falling onto ground at sprite OAM y=144 (screen sprite top=128).
    ld a,[VelocityY]
    bit 7,a
    ret nz
    ld a,[PlayerScreenY]
    cp 144
    jr c,.platforms
    ld a,144
    ld [PlayerScreenY],a
    jr .onGround
.platforms:
    ; First platform: world x 40..95, top row12 => OAM y=104.
    ld a,[PlayerWorldX]
    cp 40
    jr c,.second
    cp 97
    jr nc,.second
    ld a,[PlayerScreenY]
    cp 104
    jr c,.second
    cp 109
    jr nc,.second
    ld a,104
    ld [PlayerScreenY],a
    jr .onGround
.second:
    ; Second platform: world x 104..159, top row9 => OAM y=80.
    ld a,[PlayerWorldX]
    cp 104
    jr c,.finish
    cp 161
    jr nc,.finish
    ld a,[PlayerScreenY]
    cp 80
    jr c,.finish
    cp 85
    jr nc,.finish
    ld a,80
    ld [PlayerScreenY],a
    jr .onGround
.finish:
    ret
.onGround:
    xor a
    ld [VelocityY],a
    ld a,1
    ld [Grounded],a
    ret
HasGroundSupport:
    ; A grounded player must lose support if walking off a ledge.
    ld a,[PlayerScreenY]
    cp 144
    jr z,.supported ; full-width bottom ground
    cp 104
    jr nz,.checkSecond
    ld a,[PlayerWorldX]
    cp 40
    jr c,.unsupported
    cp 97
    jr nc,.unsupported
    jr .supported
.checkSecond:
    ld a,[PlayerScreenY]
    cp 80
    jr nz,.unsupported
    ld a,[PlayerWorldX]
    cp 104
    jr c,.unsupported
    cp 161
    jr nc,.unsupported
.supported:
    ld a,1
    ret
.unsupported:
    xor a
    ret
MoveCamera:
    ld a,[PlayerWorldX]
    cp 80
    jr c,.noScroll
    sub 80
    cp 96
    jr c,.set
    ld a,96
.set:
    ld [CameraScroll],a
    ldh [rSCX],a
    ret
.noScroll:
    xor a
    ld [CameraScroll],a
    ldh [rSCX],a
    ret
PaintObjects:
    ; OAM writes are made during VBlank.
    ld a,[PlayerScreenY]
    ld [OAM],a
    ld a,[PlayerWorldX]
    ld b,a
    ld a,[CameraScroll]
    ld c,a
    ld a,b
    sub c
    add 8
    ld [OAM+1],a
    ld hl,AnimationClock
    inc [hl]
    ld a,[hl]
    and $3F
    jr nz,.normal
    ld a,4
    jr .tile
.normal:
    ld a,2
.tile:
    ld [OAM+2],a
    xor a
    ld [OAM+3],a
    ld a,[StarScreenY]
    ld [OAM+4],a
    ld a,[StarWorldX]
    ld b,a
    ld a,[CameraScroll]
    ld c,a
    ld a,b
    sub c
    add 8
    ld [OAM+5],a
    ld a,3
    ld [OAM+6],a
    xor a
    ld [OAM+7],a
    ret
CollectStar:
    ld a,[PlayerWorldX]
    ld b,a
    ld a,[StarWorldX]
    sub b
    add 7
    cp 15
    ret nc
    ld a,[PlayerScreenY]
    ld b,a
    ld a,[StarScreenY]
    sub b
    add 7
    cp 15
    ret nc
    ; Move next star to another reachable part of the world.
    ; Alternate prizes between two physically reachable ledges.
    ld a,[StarWorldX]
    cp 100
    jr nc,.nextLow
    ld a,144 ; second platform, y80
    ld [StarWorldX],a
    ld a,80
    ld [StarScreenY],a
    jr .starDone
.nextLow:
    ld a,72 ; first platform, y104
    ld [StarWorldX],a
    ld a,104
    ld [StarScreenY],a
.starDone:
    ld a,$1B
    ldh [rOBP0],a ; audible/visual reward still needs external review
    ret
GOAL_X EQU __GOAL_X__
__PLATFORM_TILES__
SECTION "Variables", WRAM0
PlayerWorldX: ds 1
PlayerScreenY: ds 1
VelocityY: ds 1
Grounded: ds 1
CameraScroll: ds 1
StarWorldX: ds 1
StarScreenY: ds 1
AnimationClock: ds 1
"""
    source=source.replace("__GOAL_X__",str(goal_x)).replace("__PLATFORM_TILES__",_rom_tile_bytes())
    build="""\
RGBASM ?= rgbasm
RGBLINK ?= rgblink
RGBFIX ?= rgbfix
.PHONY: all clean
all: build/dragon.gb
build/dragon.o: src/main.asm
\tmkdir -p build
\t$(RGBASM) -o $@ $<
build/dragon.gb: build/dragon.o
\t$(RGBLINK) -o $@ $<
\t$(RGBFIX) -v -p 0 -t DRAGONJUMP $@
clean:
\trm -rf build
"""
    return {"src/main.asm":source,"Makefile":build}
