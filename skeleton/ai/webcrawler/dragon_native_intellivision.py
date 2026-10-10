"""Original Mattel Intellivision CP1610/STIC/AY PSG homebrew game.

IntyBASIC v1.5.1 produces real CP1610 assembly; as1600 links cartridge
bytes. The generator never distributes firmware, EXEC/GROM BIOS or keys,
and no emulator or physical Intellivision capability is inferred.
"""
from __future__ import annotations

INTELLIVISION_SOURCE=r''' ' Original Dragon STIC Quest: 1979 CP1610 native game
 ' A game for IntyBASIC and AS1600; no copyrighted commercial assets.
 OPTION EXPLICIT
 DIM playerX,playerY,gemX,gemY,enemyX,enemyY,energy,score,level
 DIM guard,ticks,rng,chime
 DEFINE 0,1,dragonArt
 DEFINE 1,1,gemArt
 DEFINE 2,1,enemyArt
 WAIT

STARTGAME:
 CLS
 playerX=40:playerY=40
 gemX=__GEMX__:gemY=__GEMY__
 enemyX=133:enemyY=74
 energy=5:score=0:level=1:guard=0:ticks=0
 rng=__SEED8__:chime=0
 SOUND 0,80,0
 PRINT AT 0 COLOR 7,"DRAGON ORIGINAL"
 PRINT AT 20 COLOR 3,"CP1610 STIC QUEST"
 PRINT AT 220 COLOR 7,"DISC MOVE  KEY RESTART"

GAMELOOP:
 WAIT
 IF CONT1.B0 THEN GOTO STARTGAME
 IF energy=0 THEN GOTO DEAD
 IF CONT1.LEFT THEN IF playerX>6 THEN playerX=playerX-1
 IF CONT1.RIGHT THEN IF playerX<151 THEN playerX=playerX+1
 IF CONT1.UP THEN IF playerY>16 THEN playerY=playerY-1
 IF CONT1.DOWN THEN IF playerY<83 THEN playerY=playerY+1
 ticks=ticks+1
 IF guard>0 THEN guard=guard-1
 IF chime>0 THEN chime=chime-1
 IF chime=0 THEN SOUND 0,80,0
 IF ABS(playerX-gemX)<9 THEN IF ABS(playerY-gemY)<9 THEN GOSUB COLLECT
 IF ticks>12 THEN GOSUB HUNT
 IF guard=0 THEN IF ABS(playerX-enemyX)<9 THEN IF ABS(playerY-enemyY)<9 THEN GOSUB COLLIDE
 SPRITE 0,playerX+$200,playerY+$100,2048+5
 SPRITE 1,gemX+$200,gemY+$100,2056+6
 SPRITE 2,enemyX+$200,enemyY+$100,2064+2
 GOTO GAMELOOP

COLLECT:
 score=score+1
 level=score/5
 level=level+1
 rng=rng+31
 gemX=12+(rng AND 127)
 rng=rng+41
 gemY=22+(rng AND 63)
 IF score=5 THEN energy=5
 IF score=10 THEN energy=5
 SOUND 0,78,12
 chime=9
 RETURN

HUNT:
 ticks=0
 IF enemyX<playerX THEN enemyX=enemyX+1
 IF enemyX>playerX THEN enemyX=enemyX-1
 IF enemyY<playerY THEN enemyY=enemyY+1
 IF enemyY>playerY THEN enemyY=enemyY-1
 RETURN

COLLIDE:
 IF energy>0 THEN energy=energy-1
 guard=28
 enemyX=142:enemyY=72
 SOUND 0,146,13
 chime=13
 RETURN

DEAD:
 WAIT
 SOUND 0,80,0
 PRINT AT 101 COLOR 2,"DRAGON DOWN"
 PRINT AT 141 COLOR 7,"KEY 0 RETRIES"
 IF CONT1.B0 THEN GOTO STARTGAME
 GOTO DEAD

dragonArt:
 BITMAP "..XXXX.."
 BITMAP ".XXXXXX."
 BITMAP "XX.XX.XX"
 BITMAP "XXXXXXXX"
 BITMAP "XXXXXXX."
 BITMAP ".XXXXXX."
 BITMAP "..XXXX.."
 BITMAP ".XX..XX."
gemArt:
 BITMAP "...XX..."
 BITMAP "..XXXX.."
 BITMAP ".XXXXXX."
 BITMAP "XXXXXXXX"
 BITMAP "XXXXXXXX"
 BITMAP ".XXXXXX."
 BITMAP "..XXXX.."
 BITMAP "...XX..."
enemyArt:
 BITMAP "XX....XX"
 BITMAP ".XX..XX."
 BITMAP "..XXXX.."
 BITMAP ".XXXXXX."
 BITMAP "XXXXXXXX"
 BITMAP "XX.XX.XX"
 BITMAP ".XX..XX."
 BITMAP "XX....XX"
'''
MAKEFILE='''# IntyBASIC (CP1610) + AS1600 (jzIntv) open homebrew toolchain.
INTYBASIC ?= intybasic
AS1600 ?= as1600
all: build/dragon.bin
build/dragon.asm: src/main.bas
\tmkdir -p build
\t$(INTYBASIC) $< $@
build/dragon.bin: build/dragon.asm
\t$(AS1600) -o build/dragon $<
\ttest -s $@
clean:
\trm -rf build
'''
def intellivision_source(seed:int)->dict[str,str]:
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError("Intellivision seed must be uint32")
    seed=seed or 1
    return {
       "src/main.bas":INTELLIVISION_SOURCE.replace("__SEED8__",str(seed%211+1))
            .replace("__GEMX__",str(20+seed%95))
            .replace("__GEMY__",str(25+(seed//37)%51)),
       "Makefile":MAKEFILE,
       "README.port.md":(
        "# Original Intellivision 1979 CP1610 game\n"
        "Requires IntyBASIC v1.5.1 + AS1600, installed separately. "
        "Real STIC 8 MOB sprites, GRAM 8x8 original tiles, Intellivision "
        "hand-controller 16-way disc/keypad and 3-voice AY-3-8914 PSG. "
        "Gameplay handles crystal collection, increasing levels, autonomous "
        "pursuer, invulnerability, health depletion and restart. "
        "Emitted source and instructions are not a compiled cartridge; "
        "jzIntv replay, legal device access and physical controller tests "
        "are separate. No EXEC/GROM proprietary firmware is included.\n"),
    }
