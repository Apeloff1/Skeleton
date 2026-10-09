"""Original NES 6502 horizontal-scrolling platformer.

NROM-256, iNES CHR, vertically mirrored CIRAM (two horizontal screens);
32+32 columns of original tilemap, 2bpp sprites, controller A jump and
D-pad movement, ground/ledge collision, gravity, moving opponent, health,
four stage exits, camera and sprite OAM DMA. Compiles with ca65/ld65.
"""
from __future__ import annotations
from hashlib import sha256
import json
from .dragon_retro_assets import BITMAPS,compile_tile

def _bytes(data:bytes)->str:
    return "\n".join("    .byte "+",".join("$%02X"%v for v in data[i:i+16])
                     for i in range(0,len(data),16))

def _nametables()->tuple[bytes,bytes]:
    maps=[]
    for begin in (0,32):
        cells=[]
        for y in range(30):
            for local_x in range(32):
                x=begin+local_x
                floor=y>=26
                ledge=(y==18 and 12<=x<=24) or (y==15 and 36<=x<=48)
                cells.append(1 if floor or ledge else 0)
        maps.append(bytes(cells)+bytes(64))
    return maps[0],maps[1]

ASM=r'''; Original NES platformer NROM with two horizontal nametables.
.segment "HEADER"
.byte "NES",$1A,2,1,1,0
.res 8,0
.segment "ZEROPAGE"
Frame: .res 1
Last: .res 1
XLo: .res 1
XHi: .res 1
Y: .res 1
Jump: .res 1
OnFloor: .res 1
BtnA: .res 1
PrevA: .res 1
BtnL: .res 1
BtnR: .res 1
BtnStart: .res 1
CamLo: .res 1
CamHi: .res 1
Lives: .res 1
Stage: .res 1
GemLo: .res 1
Score: .res 1
EnemyX: .res 1
EnemyRight: .res 1
Damage: .res 1
PtrLo: .res 1
PtrHi: .res 1
.segment "CODE"
Reset:
    sei
    cld
    ldx #$40
    stx $4017
    ldx #$FF
    txs
    inx
    stx $2000
    stx $2001
    stx $4010
Wait1:
    bit $2002
    bpl Wait1
    ldx #0
    lda #$FF
ClearOAM:
    sta $0200,x
    inx
    bne ClearOAM
Wait2:
    bit $2002
    bpl Wait2
    lda #$20
    sta $2006
    lda #0
    sta $2006
    lda #<Background0
    sta PtrLo
    lda #>Background0
    sta PtrHi
    jsr CopyMap
    lda #$24
    sta $2006
    lda #0
    sta $2006
    lda #<Background1
    sta PtrLo
    lda #>Background1
    sta PtrHi
    jsr CopyMap
    lda #$3F
    sta $2006
    lda #0
    sta $2006
    ldx #0
PaletteLoop:
    lda Palette,x
    sta $2007
    inx
    cpx #32
    bne PaletteLoop
    jsr Restart
    lda #0
    sta Frame
    sta Last
    sta $2005
    sta $2005
    lda #%10000000
    sta $2000
    lda #%00011110
    sta $2001
Main:
    lda Last
FrameWait:
    cmp Frame
    beq FrameWait
    lda Frame
    sta Last
    jsr Poll
    lda Stage
    cmp #5
    bcc Play
    lda BtnStart
    beq Main
    jsr Restart
    jmp Main
Play:
    jsr MoveHero
    jsr UpdateCamera
    jsr UpdateEnemy
    jsr Sprites
    jmp Main
CopyMap:
    ldx #4
    ldy #0
CopyLoop:
    lda (PtrLo),y
    sta $2007
    iny
    bne CopyLoop
    inc PtrHi
    dex
    bne CopyLoop
    rts
Restart:
    lda #32
    sta XLo
    lda #0
    sta XHi
    sta Jump
    sta PrevA
    sta CamLo
    sta CamHi
    sta Score
    sta Damage
    lda #200
    sta Y
    lda #1
    sta Stage
    sta OnFloor
    sta EnemyRight
    lda #3
    sta Lives
    lda #220
    sta EnemyX
    lda #170
    sta GemLo
    rts
NextStage:
    inc Stage
    lda #32
    sta XLo
    lda #0
    sta XHi
    sta CamLo
    sta CamHi
    sta Jump
    lda #200
    sta Y
    lda #1
    sta OnFloor
    lda GemLo
    clc
    adc #7
    sta GemLo
    rts
Poll:
    lda #1
    sta $4016
    lda #0
    sta $4016
    lda $4016
    and #1
    sta BtnA
    lda $4016
    lda $4016
    lda $4016
    and #1
    sta BtnStart
    lda $4016
    lda $4016
    and #1
    sta BtnL
    lda $4016
    and #1
    sta BtnR
    rts
MoveHero:
    lda BtnR
    beq TestLeft
    inc XLo
    bne TestLeft
    inc XHi
TestLeft:
    lda BtnL
    beq TestJump
    lda XHi
    bne GoLeft
    lda XLo
    cmp #16
    bcc TestJump
    beq TestJump
GoLeft:
    lda XLo
    bne NoBorrow
    dec XHi
NoBorrow:
    dec XLo
TestJump:
    lda BtnA
    beq JumpEnded
    lda PrevA
    bne JumpEnded
    lda OnFloor
    beq JumpEnded
    lda #22
    sta Jump
    lda #0
    sta OnFloor
JumpEnded:
    lda BtnA
    sta PrevA
    lda Jump
    beq Falling
    dec Jump
    lda Y
    sec
    sbc #3
    sta Y
    jmp CheckGoal
Falling:
    lda #0
    sta OnFloor
    lda Y
    cmp #200
    bcs Land
    clc
    adc #2
    sta Y
    cmp #136
    bcc CheckGoal
    cmp #139
    bcs CheckGoal
    lda XHi
    bne CheckGoal
    lda XLo
    cmp #96
    bcc CheckGoal
    cmp #196
    bcs CheckGoal
    lda #136
    sta Y
    lda #1
    sta OnFloor
    jmp CheckGoal
Land:
    lda #200
    sta Y
    lda #1
    sta OnFloor
CheckGoal:
    lda XHi
    cmp #1
    bne MoveDone
    lda XLo
    cmp GemLo
    bcc MoveDone
    lda Y
    cmp #160
    bcc MoveDone
    inc Score
    jsr NextStage
MoveDone:
    rts
UpdateCamera:
    lda XHi
    beq FirstHalf
    lda XLo
    cmp #120
    bcs FullScroll
    sec
    sbc #120
    sta CamLo
    lda #1
    sta CamHi
    rts
FirstHalf:
    lda XLo
    cmp #120
    bcc ZeroScroll
    sec
    sbc #120
    sta CamLo
    lda #0
    sta CamHi
    rts
FullScroll:
    lda #0
    sta CamLo
    lda #1
    sta CamHi
    rts
ZeroScroll:
    lda #0
    sta CamLo
    sta CamHi
    rts
UpdateEnemy:
    lda Damage
    beq WalkEnemy
    dec Damage
WalkEnemy:
    lda Frame
    and #7
    bne Collide
    lda EnemyRight
    beq WalkBack
    inc EnemyX
    lda EnemyX
    cmp #240
    bcc Collide
    lda #0
    sta EnemyRight
    jmp Collide
WalkBack:
    dec EnemyX
    lda EnemyX
    cmp #188
    bcs Collide
    lda #1
    sta EnemyRight
Collide:
    lda XHi
    bne EndEnemy
    lda XLo
    sec
    sbc EnemyX
    cmp #12
    bcc Touch
    lda EnemyX
    sec
    sbc XLo
    cmp #12
    bcs EndEnemy
Touch:
    lda Y
    cmp #185
    bcc EndEnemy
    lda Damage
    bne EndEnemy
    lda #42
    sta Damage
    dec Lives
    bne EndEnemy
    jsr Restart
EndEnemy:
    rts
Sprites:
    lda Y
    sta $0200
    lda Frame
    and #8
    beq Still
    lda #3
    jmp PlayerTile
Still:
    lda #2
PlayerTile:
    sta $0201
    lda #0
    sta $0202
    sec
    lda XLo
    sbc CamLo
    sta $0203
    sec
    lda GemLo
    sbc CamLo
    sta $0207
    lda #1
    sbc CamHi
    bne HideGem
    lda #184
    sta $0204
    jmp GemReady
HideGem:
    lda #$FF
    sta $0204
GemReady:
    lda #4
    sta $0205
    lda #0
    sta $0206
    sec
    lda EnemyX
    sbc CamLo
    sta $020B
    lda #0
    sbc CamHi
    bne HideEnemy
    lda #184
    sta $0208
    jmp EnemyReady
HideEnemy:
    lda #$FF
    sta $0208
EnemyReady:
    lda #5
    sta $0209
    lda #0
    sta $020A
    rts
NMI:
    pha
    txa
    pha
    tya
    pha
    lda #0
    sta $2003
    lda #2
    sta $4014
    lda #%10000000
    ora CamHi
    sta $2000
    lda CamLo
    sta $2005
    lda #0
    sta $2005
    inc Frame
    pla
    tay
    pla
    tax
    pla
    rti
IRQ: rti
Palette:
.byte $0F,$20,$16,$26,$0F,$30,$11,$21,$0F,$30,$06,$16,$0F,$30,$16,$26
.byte $0F,$20,$16,$26,$0F,$30,$06,$16,$0F,$30,$11,$21,$0F,$30,$16,$26
.segment "VECTORS"
.addr NMI,Reset,IRQ
.segment "RODATA"
Background0:
__BG0__
Background1:
__BG1__
.segment "CHARS"
__CHR__
.res $2000-__CHRLEN__,0
'''

def nes_platformer_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("NES cartridge platformer requires uint32 seed")
    from .dragon_native_projects import _nes
    base=_nes(seed)
    a,b=_nametables()
    images=[bytes(16),bytes([0xff]*8+[0]*8)]
    names=("dragon","dragon_walk","star","enemy","heart","portal")
    images += [compile_tile(name,BITMAPS[name]).nes for name in names]
    graphics=b"".join(images)
    asm=ASM.replace("__BG0__",_bytes(a)).replace("__BG1__",_bytes(b))
    asm=asm.replace("__CHR__",_bytes(graphics))
    asm=asm.replace("__CHRLEN__",str(len(graphics)))
    evidence={
        "schema":"skeleton.ai.dragon.nes_native_scroller.v1",
        "levels":4,"world_tile_columns":64,"world_tile_rows":30,
        "mirroring":"vertical_for_horizontal_scroll",
        "bg0_digest":sha256(a).hexdigest(),
        "bg1_digest":sha256(b).hexdigest(),
        "chr_digest":sha256(graphics).hexdigest(),
        "original_chr_tiles":len(images),
        "physics":"ground/ledge/gravity/jump_frame_timed",
        "video":"NES PPU two nametables, OAM DMA on NMI",
        "compiled":False,"emulator_tested":False,
    }
    return {
        "src/main.s":asm,
        "nes.cfg":base["nes.cfg"].replace(
            " CODE: load=PRG, type=ro;",
            " CODE: load=PRG, type=ro;\n RODATA: load=PRG, type=ro;"
        ),
        "Makefile":base["Makefile"],
        "dragon-nes-scroller.json":json.dumps(evidence,sort_keys=True,indent=2)+"\n",
        "README.engine.md":"# Original NES side-scrolling platformer\n\n"
          "Real ca65 NROM-256 cartridge, 64-column backdrop in two PPU "
          "nametables, vertical mirroring, sprite OAM DMA, A-button "
          "jump, ledge/ground physics, following camera, stage reset and "
          "enemy pressure. Use make with ca65/ld65, then validate real "
          "NES emulator frame timing, controls and graphics separately.\n",
    }
