"""The Dragon's era-spanning native game target catalog.

A platform is a hardware/OS target, not a visual filter. Availability has
specific meanings: native_source produces compilable-intent platform source
(no claim of a successful build); toolchain_adapter requires an independently
installed SDK and a validated adapter; licensed requires partner access.
All templates are original homebrew, not commercial game copies, BIOS or keys.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Status = Literal["native_source", "toolchain_adapter", "licensed_sdk"]
@dataclass(frozen=True)
class ConsoleTarget:
    id: str
    family: str
    generation: str
    year: int
    cpu: str
    graphics: str
    sound: str
    input: str
    toolchain: str
    output: str
    status: Status
    max_colors: int
    max_width: int
    max_height: int
    notes: str = ""

def _t(id, family, generation, year, cpu, graphics, sound, input, toolchain,
       output, status="toolchain_adapter", colors=256, width=320, height=240, notes=""):
    return ConsoleTarget(id,family,generation,year,cpu,graphics,sound,input,
                         toolchain,output,status,colors,width,height,notes)

TARGETS: tuple[ConsoleTarget,...] = (
    _t("atari_2600","Atari","2nd generation",1977,"6507","TIA scanline","TIA",
       "joystick","DASM / cc65","bin",colors=128,width=160,height=192),
    _t("intellivision","Mattel","2nd generation",1979,"CP1610","STIC","AY-3-8914",
       "disc controller","as1600","bin",colors=16,width=160,height=96),
    _t("colecovision","Coleco","2nd generation",1982,"Z80","TMS9928A","SN76489",
       "keypad joystick","SDCC / z88dk","rom",colors=16,width=256,height=192),
    _t("commodore_64","Commodore","8-bit home computer",1982,"6510","VIC-II","SID",
       "keyboard / joystick","cc65","prg","native_source",colors=16,width=320,height=200),
    _t("zx_spectrum","Sinclair","8-bit home computer",1982,"Z80","attribute bitmap","beeper / AY",
       "keyboard","z88dk","tap",colors=15,width=256,height=192),
    _t("apple_ii","Apple","8-bit home computer",1977,"6502","hi-res NTSC","beeper",
       "keyboard / paddle","cc65","dsk",colors=6,width=280,height=192),
    _t("nes","Nintendo","8-bit",1983,"Ricoh 2A03","PPU tiles","APU",
       "NES controller","cc65 / ca65","nes",colors=54,width=256,height=240),
    _t("master_system","Sega","8-bit",1985,"Z80","VDP tiles","SN76489",
       "2-button pad","SDCC / devkitSMS","sms","native_source",colors=64,width=256,height=192),
    _t("game_boy","Nintendo","handheld 8-bit",1989,"SM83","2bpp tiles / OAM","DMG APU",
       "D-pad A B Start Select","RGBDS","gb","native_source",4,160,144),
    _t("game_boy_color","Nintendo","handheld 8-bit color",1998,"SM83","CGB tile palettes","CGB APU",
       "D-pad A B Start Select","RGBDS","gbc","native_source",colors=32768,width=160,height=144),
    _t("game_gear","Sega","handheld 8-bit",1990,"Z80","SMS-derived LCD","PSG",
       "D-pad 2-button","SDCC / devkitSMS","gg","native_source",colors=4096,width=160,height=144),
    _t("lynx","Atari","handheld 8/16-bit",1989,"65C02","Suzy blitter","Mikey",
       "D-pad A B","cc65 / Lynx SDK","lnx",colors=4096,width=160,height=102),
    _t("turbografx_16","NEC","16-bit era",1987,"HuC6280","HuC6270 VDC","HuC6280 PSG",
       "2/6-button pad","HuC / pceas","pce",colors=512,width=256,height=224),
    _t("genesis","Sega","16-bit",1988,"68000 + Z80","VDP tiles / sprites","YM2612 / PSG",
       "3/6-button pad","SGDK","bin","native_source",colors=512,width=320,height=224),
    _t("snes","Nintendo","16-bit",1990,"65C816","PPU Mode 1-7","SPC700",
       "SNES pad","PVSnesLib","sfc","native_source",colors=32768,width=256,height=224),
    _t("neo_geo","SNK","arcade 16-bit",1990,"68000 + Z80","sprite hardware","YM2610",
       "arcade stick","NGDEVKIT","neo",colors=65536,width=320,height=224),
    _t("amiga_500","Commodore","16/32-bit computer",1987,"68000","OCS blitter / copper","Paula",
       "mouse joystick","vbcc / vasm","adf",colors=4096,width=320,height=256),
    _t("atari_st","Atari","16/32-bit computer",1985,"68000","Shifter","YM2149",
       "mouse joystick","vasm / GCC m68k","st",colors=512,width=320,height=200),
    _t("dos_8086","IBM PC compatible","DOS early",1981,"8086","CGA / text","PC speaker",
       "keyboard","OpenWatcom","exe",colors=16,width=320,height=200),
    _t("dos_vga","IBM PC compatible","DOS VGA era",1990,"386","VGA mode 13h","AdLib / SB",
       "keyboard","DJGPP","exe","native_source",256,320,200),
    _t("windows_95","Microsoft","Win9x 2D",1995,"x86","DirectDraw / Win32 GDI","DirectSound",
       "keyboard/gamepad","OpenWatcom / MinGW","exe",colors=16777216,width=640,height=480),
    _t("windows_xp","Microsoft","Win32 DirectX era",2001,"x86","Direct3D 9","DirectSound",
       "DirectInput","MSVC / DirectX SDK","exe",colors=16777216,width=800,height=600),
    _t("ps1","Sony PlayStation","32-bit",1994,"MIPS R3000A","GPU polygons / TIM","SPU",
       "PlayStation controller","PSn00bSDK","exe","native_source",colors=16777216,width=320,height=240),
    _t("saturn","Sega","32-bit",1994,"dual SH-2","VDP1 + VDP2","SCSP",
       "Saturn pad","Jo Engine / libyaul","iso",colors=16777216,width=320,height=240),
    _t("nintendo_64","Nintendo","64-bit",1996,"MIPS VR4300","RDP / RSP","AI DAC",
       "analog stick","libdragon","z64","native_source",colors=16777216,width=320,height=240),
    _t("dreamcast","Sega","128-bit era",1998,"SH-4","PowerVR2","AICA",
       "Dreamcast controller","KallistiOS","cdi",colors=16777216,width=640,height=480),
    _t("game_boy_advance","Nintendo","handheld 32-bit",2001,"ARM7TDMI","Mode 3/4 sprites","PSG / PCM",
       "D-pad AB LR","devkitARM / libgba","gba","native_source",colors=32768,width=240,height=160),
    _t("gamecube","Nintendo","6th generation",2001,"PowerPC Gekko","Flipper","DSP",
       "GameCube controller","devkitPPC / libogc","dol",colors=16777216,width=640,height=480),
    _t("ps2","Sony PlayStation","6th generation",2000,"Emotion Engine","Graphics Synthesizer","SPU2",
       "DualShock 2","ps2dev / PS2SDK","elf",colors=16777216,width=640,height=448),
    _t("xbox_original","Microsoft Xbox","6th generation",2001,"x86","NV2A","MCPX",
       "Xbox controller","nxdk","xbe","native_source",colors=16777216,width=640,height=480),
    _t("nintendo_ds","Nintendo","dual-screen handheld",2004,"ARM9 + ARM7","2D engines + 3D","DS audio",
       "touch / buttons","devkitARM / libnds","nds","native_source",colors=262144,width=256,height=192),
    _t("psp","Sony PlayStation","handheld 3D",2004,"MIPS Allegrex","GU","PSP audio",
       "PSP buttons","PSPSDK","pbp","native_source",colors=16777216,width=480,height=272),
    _t("wii","Nintendo","7th generation",2006,"Broadway PPC","Hollywood","DSP",
       "Wii Remote","devkitPPC / libogc","dol",colors=16777216,width=640,height=480),
    _t("ps3","Sony PlayStation","7th generation",2006,"Cell","RSX","SPU audio",
       "DualShock 3","PS3 homebrew PSL1GHT","self",colors=16777216,width=1280,height=720,
       notes="Hardware execution subject to platform and homebrew constraints"),
    _t("xbox_360","Microsoft Xbox","7th generation",2005,"PowerPC Xenon","Xenos","XMA",
       "Xbox 360 pad","nonstandard homebrew / licensed XDK","xex","licensed_sdk",16777216,1280,720),
    _t("nintendo_3ds","Nintendo","stereo handheld",2011,"ARM11 + ARM9","PICA200","3DS audio",
       "circle pad / touch","devkitARM / libctru","3dsx",colors=16777216,width=400,height=240),
    _t("wii_u","Nintendo","8th generation",2012,"PowerPC Espresso","Latte","Wii U audio",
       "GamePad touch","devkitPPC / wut","wuhb",colors=16777216,width=1280,height=720),
    _t("ps_vita","Sony PlayStation","handheld 8th generation",2011,"ARM Cortex-A9","SGX543","Vita audio",
       "touch / buttons","VitaSDK","vpk",colors=16777216,width=960,height=544),
    _t("ps4","Sony PlayStation","8th generation",2013,"x86-64","GCN GPU","PS4 audio",
       "DualShock 4","Sony licensed SDK","pkg","licensed_sdk",16777216,1920,1080),
    _t("xbox_one","Microsoft Xbox","8th generation",2013,"x86-64","GCN GPU","Xbox One audio",
       "Xbox pad","Microsoft GDKX","xvc","licensed_sdk",16777216,1920,1080),
    _t("nintendo_switch","Nintendo","hybrid 8th generation",2017,"ARMv8","Tegra X1","Switch audio",
       "Joy-Con / Pro controller","devkitA64 / libnx","nro",colors=16777216,width=1280,height=720),
    _t("ps5","Sony PlayStation","9th generation",2020,"x86-64","RDNA 2","Tempest Audio",
       "DualSense","Sony licensed SDK","pkg","licensed_sdk",16777216,1920,1080),
    _t("xbox_series","Microsoft Xbox","9th generation",2020,"x86-64","RDNA 2","Spatial Audio",
       "Xbox Series pad","Microsoft GDKX","xvc","licensed_sdk",16777216,1920,1080),
    _t("pc_linux","Open PC","modern desktop",2026,"x86-64 / arm64","SDL2 / OpenGL","SDL audio",
       "keyboard / gamepad","CMake + SDL2","elf","native_source",16777216,1280,720),
    _t("pc_windows","Open PC","modern desktop",2026,"x86-64 / arm64","SDL2 / D3D","SDL audio",
       "keyboard / gamepad","CMake + SDL2","exe","native_source",16777216,1280,720),
    _t("pc_macos","Apple Mac","modern desktop",2026,"arm64 / x86-64","SDL2 / Metal","CoreAudio",
       "keyboard / gamepad","CMake + SDL2","app","native_source",16777216,1280,720),
    _t("steam_deck","Valve","portable PC",2022,"Zen 2","RDNA 2","PipeWire",
       "Steam Input","CMake + SDL2 / Proton","elf","native_source",16777216,1280,800),
)
CATALOG = {target.id: target for target in TARGETS}
assert len(CATALOG)==len(TARGETS), "duplicate platform identity"

STYLES = (
    "arcade_score_attack","fixed_screen_puzzle","top_down_adventure",
    "side_scrolling_platformer","metroidvania","tactical_rpg","turn_based_rpg",
    "roguelike","bullet_hell","run_and_gun","puzzle_platformer",
    "visual_novel","rhythm_game","fighting_game","racing",
    "first_person_shooter","third_person_action","survival_horror",
    "immersive_sim","city_builder","real_time_strategy",
    "grand_strategy","simulation","sports","cozy_farming",
    "sandbox_builder","educational","party_game","local_coop","narrative_adventure",
)

def target_catalog(*, family: str | None = None) -> tuple[dict, ...]:
    from .dragon_game_blueprints import GENRES
    desktop={"pc_linux","pc_windows","pc_macos","steam_deck"}
    source_ids={"game_boy","game_boy_color","nes","master_system","game_gear","snes","commodore_64","genesis","game_boy_advance","ps1",
                "xbox_original","dos_vga","nintendo_64","nintendo_ds","psp"}|desktop
    rows=[]
    for t in TARGETS:
        if family is not None and t.family!=family:
            continue
        row=asdict(t)
        row["supported_styles"]=(
            tuple(sorted(set(GENRES)|{"rhythm_game","fixed_screen_puzzle"})) if t.id in desktop
            else ("arcade_score_attack","side_scrolling_platformer") if t.id=="game_boy"
            else ("arcade_score_attack",) if t.id in source_ids else ()
        )
        rows.append(row)
    return tuple(rows)

def demand_target(target_id: str) -> ConsoleTarget:
    if not isinstance(target_id,str) or target_id not in CATALOG:
        raise ValueError("unknown hardware target")
    return CATALOG[target_id]

def practice_matrix() -> tuple[dict, ...]:
    """Truthful per-style SDK source coverage; never count catalog-only targets."""
    rows=target_catalog()
    matrix=[]
    for style in STYLES:
        available=tuple(r["id"] for r in rows if (
            r["status"]=="native_source" and style in r["supported_styles"]
        ))
        matrix.append({
            "style":style,
            "supported_hardware_count":len(available),
            "native_emitters":available,
            "catalog_hardware_count":len(TARGETS),
            "remaining_adapter_work":len(available)<len(TARGETS),
            "coverage_claim":"source_supported_not_compiled",
        })
    return tuple(matrix)
