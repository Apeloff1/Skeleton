"""Actual Nintendo Game Boy hardware APU channel-1 reward audio.

The D-pad game and the scrolling platformer share native NRxx sound register
setup. Only original short square-wave sounds are generated, not sampled or
commercial game audio. The one-screen game has a one-time reward latch; the
scrolling world triggers a distinct chime on each newly moved collectible.
"""
from __future__ import annotations
import re

APU_ROUTINES=r"""
; Game Boy NR52 power, NR50 master volume, NR51 output, NR11 duty,
; NR12 envelope, NR13/NR14 frequency + trigger. No network audio.
SetupSound:
    xor a
    ld [RewardLatch],a
    ld a,$80
    ldh [$FF26],a
    ld a,$77
    ldh [$FF24],a
    ld a,$11
    ldh [$FF25],a
    ld a,$80
    ldh [$FF11],a
    ld a,$F2
    ldh [$FF12],a
    ret
PlayRewardOnce:
    ld hl,RewardLatch
    ld a,[hl]
    and a
    ret nz
    ld a,1
    ld [hl],a
    jp PlayReward
PlayReward:
    ld a,$A0
    ldh [$FF13],a
    ld a,$87
    ldh [$FF14],a
    ret
"""

def enrich_native_gb_sound(source:str,*,scrolling:bool)->str:
    if not isinstance(source,str):raise ValueError("GB APU requires assembly source")
    stack="    ld sp,$FFFE" if scrolling else "    ld sp, $FFFE"
    if stack not in source or 'SECTION "Variables", WRAM0' not in source:
        raise ValueError("Game Boy firmware bootstrap not found")
    source=source.replace(stack,stack+"\n    call SetupSound",1)
    source=source.replace('SECTION "Variables", WRAM0',
        APU_ROUTINES+'\nSECTION "Variables", WRAM0\nRewardLatch: ds 1',1)
    if scrolling:
        # Called on a new collectible; the goal is moved on success,
        # therefore repeated frame-by-frame false rewards are avoided.
        # RGBDS source generators differ in comma spacing; match the
        # exact pair of hardware instructions rather than literal styling.
        trigger=(r"(?m)^[ \t]*ld a,\s*\$1B[ \t]*\n"
                 r"[ \t]*ldh \[rOBP0\],\s*a(?:[ \t]*;[^\n]*)?$")
        source,count=re.subn(trigger,lambda m:m.group(0)+"\n    call PlayReward",source,count=1)
        if count!=1:raise ValueError("scrolling game reward unavailable")
    else:
        trigger=(r"(?m)^[ \t]*ld a,\s*\$1B[ \t]*\n"
                 r"[ \t]*ldh \[rOBP0\],\s*a(?:[ \t]*;[^\n]*)?$")
        source,count=re.subn(trigger,lambda m:m.group(0)+"\n    call PlayRewardOnce",source,count=1)
        if count!=1:raise ValueError("cartridge reward unavailable")
    return source
