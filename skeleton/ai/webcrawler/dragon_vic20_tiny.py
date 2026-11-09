"""Unexpanded 5 KiB Commodore VIC-20 game with NO C runtime.

The earlier cc65/conio build exceeded the unexpanded VIC-20 memory.
This implementation uses a native 6502 BASIC SYS entry + direct VIC-I
screen/color RAM and Commodore KERNAL GETIN. Linked by ca65/ld65 into
a standard VIC-20 PRG at $1001 with an exact RAM budget below $1E00.
No third-party ROMs, BASIC interpreter sources or external graphics.
"""
from __future__ import annotations

ASM=r'''; Original Dragon 5K VIC20 homebrew, direct 6502/KERNAL.
; BASIC SYS 4109 at $1001; actual code at $100D, unexpanded memory.
PlayerX = $1C00
PlayerY = $1C01
GemX = $1C02
GemY = $1C03
EnemyX = $1C04
EnemyY = $1C05
Score = $1C06
Stage = $1C07
Lives = $1C08
Frame = $1C09
Char = $1C0A
Seed = $1C0B
PtrLo = $FB
PtrHi = $FC
Screen = $1E00
ColorRAM = $9600
VIC_BORDER = $900F
VIC_VOLUME = $900E
KERNAL_GETIN = $FFE4
.segment "LOADHDR"
.word $1001
.segment "CODE"
.word BasicEnd
.word 10
.byte $9E
.byte "4109",0
BasicEnd:
.word 0
Start:
    jsr Reset
GameLoop:
    jsr Paint
KeyLoop:
    jsr KERNAL_GETIN
    beq KeyLoop
    cmp #$51
    beq Quit
    cmp #$52
    beq Restart
    ldx Lives
    beq GameLoop
    cmp #$41
    bne CheckRight
    lda PlayerX
    cmp #1
    beq MoveDone
    dec PlayerX
    jmp MoveDone
CheckRight:
    cmp #$44
    bne CheckUp
    lda PlayerX
    cmp #20
    bcs MoveDone
    inc PlayerX
    jmp MoveDone
CheckUp:
    cmp #$57
    bne CheckDown
    lda PlayerY
    cmp #4
    bcc MoveDone
    beq MoveDone
    dec PlayerY
    jmp MoveDone
CheckDown:
    cmp #$53
    beq GoDown
    jmp GameLoop
GoDown:
    lda PlayerY
    cmp #21
    bcs MoveDone
    inc PlayerY
MoveDone:
    jsr Update
    jmp GameLoop
Restart:
    jsr Reset
    jmp GameLoop
Quit:
    rts
Reset:
    lda #__SEED__
    sta Seed
    lda #5
    sta PlayerX
    sta Lives
    lda #6
    sta PlayerY
    lda #16
    sta GemX
    lda #10
    sta GemY
    lda #19
    sta EnemyX
    lda #18
    sta EnemyY
    lda #1
    sta Stage
    lda #0
    sta Score
    sta Frame
    lda #$0E
    sta VIC_BORDER
    lda #$0F
    sta VIC_VOLUME
    rts
Update:
    lda PlayerX
    cmp GemX
    bne EnemyMove
    lda PlayerY
    cmp GemY
    bne EnemyMove
    inc Score
    lda Score
    lsr
    lsr
    clc
    adc #1
    sta Stage
    lda Seed
    asl
    eor Score
    clc
    adc #7
    sta Seed
    and #$0F
    clc
    adc #2
    sta GemX
    lda Seed
    lsr
    and #$0F
    clc
    adc #5
    sta GemY
    lda #$08
    sta VIC_VOLUME
EnemyMove:
    inc Frame
    lda Frame
    and #3
    bne Collision
    lda EnemyX
    cmp PlayerX
    beq EnemyYMove
    bcc EnemyRight
    dec EnemyX
    jmp EnemyYMove
EnemyRight:
    inc EnemyX
EnemyYMove:
    lda EnemyY
    cmp PlayerY
    beq Collision
    bcc EnemyDown
    dec EnemyY
    jmp Collision
EnemyDown:
    inc EnemyY
Collision:
    lda EnemyX
    cmp PlayerX
    bne UpdateDone
    lda EnemyY
    cmp PlayerY
    bne UpdateDone
    dec Lives
    lda #19
    sta EnemyX
    lda #18
    sta EnemyY
UpdateDone:
    rts
Paint:
    ldx #0
    lda #$20
Clear:
    sta Screen,x
    sta Screen+$100,x
    inx
    bne Clear
    ; original heart/life counter: 5 vertical status squares
    ldx #0
DrawHealth:
    cpx Lives
    bcs HealthDone
    lda #$2A
    sta Screen+1,x
    inx
    cpx #5
    bcc DrawHealth
HealthDone:
    lda #$2A
    sta Char
    ldx GemX
    ldy GemY
    jsr DrawAt
    lda #$58
    sta Char
    ldx EnemyX
    ldy EnemyY
    jsr DrawAt
    lda #$44
    sta Char
    ldx PlayerX
    ldy PlayerY
    jsr DrawAt
    ; collect score in the screen's top right (mod 10)
    lda Score
    and #$0F
    clc
    adc #$30
    sta Screen+20
    rts
DrawAt:
    lda #<Screen
    sta PtrLo
    lda #>Screen
    sta PtrHi
    txa
    clc
    adc PtrLo
    sta PtrLo
    bcc RowLoop
    inc PtrHi
RowLoop:
    cpy #0
    beq Place
    clc
    lda PtrLo
    adc #22
    sta PtrLo
    bcc RowCarry
    inc PtrHi
RowCarry:
    dey
    jmp RowLoop
Place:
    ldy #0
    lda Char
    sta (PtrLo),y
    rts
'''
CONFIG=r'''# Native 5 KiB unexpanded VIC20. Source code and state fit $1001-$1DFF.
MEMORY {
 LOAD: start=$0000, size=$0002, type=ro, file=%O;
 PRG: start=$1001, size=$0BFF, type=ro, file=%O;
}
SEGMENTS {
 LOADHDR: load=LOAD, type=ro;
 CODE: load=PRG, type=ro;
}
'''
MAKE=r'''CA65 ?= ca65
LD65 ?= ld65
all: build/dragon.prg
build/main.o: src/main.s
	@mkdir -p build
	$(CA65) -o $@ $<
build/dragon.prg: build/main.o vic20.cfg
	$(LD65) -C vic20.cfg -o $@ $<
clean:
	rm -rf build
'''
def vic20_tiny_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("VIC20 native game seed must be uint32")
    return {
        "src/main.s":ASM.replace("__SEED__",str(seed%255 or 1)),
        "vic20.cfg":CONFIG,
        "Makefile":MAKE,
        "README.port.md":"# Original 5 KiB VIC-20 native 6502 game\n"
          "Run BASIC SYS 4109 after loading PRG at $1001. Native $1E00 "
          "text/video RAM, VIC-I border/tone registers, ROM KERNAL GETIN, "
          "unexpanded $1001-$1DFF source and state memory. W/A/S/D move, "
          "R reset, Q exits to BASIC; collect stars and avoid moving pursuer. "
          "Build with ca65/ld65, not cl65/conio's larger default CRT. "
          "Real unexpanded emulator/hardware verification is still required.\n",
    }
