"""Native Color Game Boy target: RGBDS color-only ROM with CGB OBJ palettes.

The original DMG design is retained for backward compatibility. This adapter
adds CGB palette RAM setup, declares a CGB-only cartridge and uses original
8x8 packed sprites. No special Nintendo tools or ROM data are distributed.
"""
from __future__ import annotations

def color_game_boy(original_asm: str, original_makefile: str, seed:int) -> dict[str,str]:
    if not isinstance(original_asm,str) or not isinstance(original_makefile,str):
        raise ValueError("RGBDS source required")
    if "DEF rOBP0 EQU $FF48" not in original_asm:
        raise ValueError("missing Game Boy palette anchor")
    if "    ld a, $82\n    ldh [rLCDC], a" not in original_asm:
        raise ValueError("missing Game Boy LCD initialization")
    # CGB-specific OBJ palette memory (OCPS/OCPD, $FF6A/$FF6B).
    asm=original_asm.replace(
        "DEF rOBP0 EQU $FF48",
        "DEF rOBP0 EQU $FF48\nDEF rOCPS EQU $FF6A\nDEF rOCPD EQU $FF6B"
    )
    hue=seed%4
    # Original CGB BGR555 palettes; each 15-bit value written low then high.
    themes=(
        (0x7FFF,0x4E95,0x220A,0x0000),
        (0x7FFF,0x6B2D,0x2CA4,0x0421),
        (0x7FFF,0x5EFC,0x18CE,0x0000),
        (0x7FFF,0x56BF,0x2D54,0x0863),
    )
    palette=themes[hue]
    palette_bytes=[n for c in palette for n in (c&0xFF,(c>>8)&0xFF)]
    palette_source="CGBObjectPalette:\n"+\
        "    db "+", ".join(f"${b:02X}" for b in palette_bytes)+"\n"
    setup="""\
    ; Native CGB object palette index 0, auto-increment.
    ld a, $80
    ldh [rOCPS], a
    ld hl, CGBObjectPalette
    ld b, 8
.loadCGBPalette:
    ld a, [hli]
    ldh [rOCPD], a
    dec b
    jr nz, .loadCGBPalette
"""
    asm=asm.replace("    ld a, $82\n    ldh [rLCDC], a",
                    setup+"    ld a, $82\n    ldh [rLCDC], a")
    if 'SECTION "Variables", WRAM0' not in asm:
        raise ValueError("missing Game Boy WRAM section")
    asm=asm.replace('SECTION "Variables", WRAM0',
                    palette_source+'\nSECTION "Variables", WRAM0')
    make=original_makefile.replace("dragon.gb","dragon.gbc")
    if "$(RGBFIX) -v -p 0 -t DRAGONLAB" not in make:
        raise ValueError("RGBDS native header command missing")
    make=make.replace("$(RGBFIX) -v -p 0 -t DRAGONLAB",
                      "$(RGBFIX) -v -p 0 -C -t DRAGONCGB")
    return {"src/main.asm":asm,"Makefile":make}
