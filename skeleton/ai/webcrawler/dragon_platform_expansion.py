"""Supplemental, evidence-conscious Dragon hardware target inventory (2026).

Each row is a concrete system or ABI family, NOT an assertion that a
native game has been compiled, that a vendor SDK is supplied, or that
online services are permitted. The base catalog stores the initial 47
platforms. This data extends the *identities* across historically relevant
families and modern desktop/mobile form factors.

Canonical row: id | family | generation | year | cpu | graphics |
sound | input | toolchain | packaged output | status.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SupplementalHardware:
    id:str
    family:str
    generation:str
    year:int
    cpu:str
    graphics:str
    sound:str
    input:str
    toolchain:str
    output:str
    status:str="toolchain_adapter"

# We do not invent SDK access. Particular output extensions denote documented
# build targets, not a generated file or compatibility certification.
_ROWS = r"""
magnavox_odyssey|Magnavox|first generation|1972|discrete logic|analog overlays|none|paddle|physical hardware research|none|historical_reference
fairchild_channel_f|Fairchild|second generation|1976|Fairchild F8|2K video RAM|mono oscillator|hand controller|F8 cross assembler|bin|toolchain_adapter
rca_studio_ii|RCA|second generation|1977|COSMAC 1802|monochrome grid|tone|keypad|1802 assembler|bin|toolchain_adapter
bally_astrocade|Bally|second generation|1977|Z80|160x102 bitmap|3 voices|joystick|Z80 assembler|bin|toolchain_adapter
atari_5200|Atari|second generation|1982|6502|ANTIC GTIA|POKEY|analog controller|cc65 atari5200|bin|toolchain_adapter
atari_7800|Atari|third generation|1984|6502C|MARIA|TIA|joystick|cc65 atari7800|a78|toolchain_adapter
vectrex|GCE|second generation|1982|6809|vector CRT|AY-3-8912|analog stick|6809 assembler|bin|toolchain_adapter
sega_sg1000|Sega|third generation|1983|Z80|TMS9918|SN76489|2-button pad|SDCC / z88dk|sg|toolchain_adapter
sega_mark_iii|Sega|third generation|1985|Z80|Sega VDP|SN76489|2-button pad|SDCC / devkitSMS|sms|toolchain_adapter
famicom_disk_system|Nintendo|8-bit disk add-on|1986|2A03|NES PPU|2C33|Famicom controller|ca65 FDS homebrew|fds|toolchain_adapter
game_boy_pocket|Nintendo|handheld DMG revision|1996|SM83|2bpp OAM|DMG APU|D-pad AB|RGBDS DMG compatibility|gb|toolchain_adapter
game_boy_light|Nintendo|handheld DMG revision|1998|SM83|2bpp OAM|DMG APU|D-pad AB|RGBDS DMG compatibility|gb|toolchain_adapter
game_boy_micro|Nintendo|GBA revision|2005|ARM7TDMI|GBA 2D|GBA audio|D-pad AB LR|devkitARM libgba|gba|toolchain_adapter
game_boy_player|Nintendo|GBA/GameCube peripheral|2003|GBA hardware|GBA LCD output|GBA audio|GameCube controller|devkitARM libgba|gba|toolchain_adapter
virtual_boy|Nintendo|stereo handheld|1995|NEC V810|dual red LED screens|stereo|dual D-pads|gccvb homebrew|vb|toolchain_adapter
wonderswan|Bandai|handheld 16-bit|1999|V30MZ|2bpp LCD|digital|buttons|WSwan SDK|ws|toolchain_adapter
wonderswan_color|Bandai|handheld 16-bit color|2000|V30MZ|color LCD|digital|buttons|WSwan SDK|wsc|toolchain_adapter
neo_geo_pocket|SNK|handheld 16-bit|1998|TLCS-900H|2bpp|PSG|stick|NGPC homebrew toolchain|ngp|toolchain_adapter
neo_geo_pocket_color|SNK|handheld 16-bit color|1999|TLCS-900H|color sprite|PSG|stick|NGPC homebrew toolchain|ngc|toolchain_adapter
pokemon_mini|Nintendo|mini handheld|2001|S1C88|monochrome LCD|buzzer|buttons|PokeMini SDK|min|toolchain_adapter
nokia_n_gage|Nokia|Symbian handheld|2003|ARM9|Series 60|Symbian sound|phone keyboard|Symbian C++ SDK|sis|toolchain_adapter
gp32|GamePark|ARM handheld|2001|ARM920T|TFT|PCM|D-pad|devkitARM GP32|gxb|toolchain_adapter
gp2x|GamePark Holdings|Linux handheld|2005|dual ARM9|framebuffer|SDL audio|buttons|Open2x SDK|gpe|toolchain_adapter
dingoo_a320|Dingoo|MIPS handheld|2009|Ingenic MIPS|TFT LCD|PCM|D-pad|Dingux toolchain|elf|toolchain_adapter
playdate|Panic|modern handheld|2022|STM32F7|1-bit LCD|audio|crank/buttons|Playdate SDK|pdx|toolchain_adapter
arduboy|Arduboy|micro handheld|2016|ATmega32u4|128x64 OLED|piezo|buttons|Arduino avr-gcc|hex|toolchain_adapter
thumby|TinyCircuits|micro handheld|2021|RP2040|monochrome OLED|piezo|buttons|MicroPython SDK|py|toolchain_adapter
analogue_pocket|Analogue|FPGA handheld|2021|FPGA|FPGA display|FPGA audio|buttons|openFPGA core|rbf|toolchain_adapter
evercade|Blaze|emulation handheld|2020|ARM|LCD|PCM|buttons|authorized SDK / emulator|elf|toolchain_adapter
zx81|Sinclair|8-bit home computer|1981|Z80|monochrome ULA|beeper|keyboard|z88dk +zx81|p|toolchain_adapter
zx_spectrum_next|Sinclair lineage|enhanced Z80 home computer|2017|Z80N|Layer 2 / sprites|AY|keyboard/gamepad|z88dk +zxn|nex|toolchain_adapter
bbc_micro|Acorn|8-bit home computer|1981|6502|6845 CRTC|SN76489|keyboard|cc65 bbc|ssd|toolchain_adapter
acorn_electron|Acorn|8-bit home computer|1983|6502|ULA|SN76489|keyboard|cc65 / BeebAsm|uef|toolchain_adapter
amstrad_cpc|Amstrad|8-bit home computer|1984|Z80|6845 gate array|AY-3-8912|keyboard|z88dk +cpc|bin|native_source
msx1|MSX|8-bit home computer|1983|Z80|TMS9918|AY-3-8910|keyboard|z88dk +msx|bin|native_source
msx2|MSX|8-bit home computer|1985|Z80|V9938|AY-3-8910|keyboard|z88dk / SDCC|rom|toolchain_adapter
msx_turbo_r|MSX|16-bit home computer|1990|R800|V9958|YM2413|keyboard|z88dk +msx|rom|toolchain_adapter
commodore_vic20|Commodore|8-bit home computer|1980|6502|VIC|VIC audio|keyboard|cc65 vic20|prg|native_source
commodore_128|Commodore|8-bit home computer|1985|8502 / Z80|VIC-II|SID|keyboard|cc65 c128|prg|native_source
commodore_plus4|Commodore|8-bit home computer|1984|7501|TED|TED|keyboard|cc65 plus4|prg|toolchain_adapter
commodore_pet|Commodore|8-bit home computer|1977|6502|text VDU|beeper|keyboard|cc65 pet|prg|toolchain_adapter
atari_400_800|Atari|8-bit computer|1979|6502|ANTIC / GTIA|POKEY|joystick|cc65 atari|xex|native_source
atari_130xe|Atari|8-bit computer|1985|6502C|ANTIC / GTIA|POKEY|joystick|cc65 atari|xex|toolchain_adapter
apple_iigs|Apple|16-bit computer|1986|65816|Super Hi-Res|Ensoniq|keyboard|ORCA / cc65|sys|toolchain_adapter
trs80_model_i|Tandy|8-bit computer|1977|Z80|text video|mono|keyboard|z88dk trs80|cmd|toolchain_adapter
ti_99_4a|Texas Instruments|16-bit computer|1981|TMS9900|TMS9918|SN76489|joystick|TI99 homebrew GCC|bin|toolchain_adapter
oric_atmos|Oric|8-bit computer|1984|6502|ULA|AY-3-8912|keyboard|cc65 atmos|tap|toolchain_adapter
sharp_x68000|Sharp|16-bit Japanese PC|1987|68000|custom sprite GPU|YM2151|keyboard|Human68k GCC|x|toolchain_adapter
nec_pc_8801|NEC|8-bit Japanese PC|1981|Z80|NEC video|YM2203|keyboard|PC-88 cross compiler|d88|toolchain_adapter
nec_pc_9801|NEC|16-bit Japanese PC|1982|8086|GDC|YM2608|keyboard|OpenWatcom PC-98|exe|toolchain_adapter
fm_towns|Fujitsu|CD-ROM era PC|1989|386|FM Towns graphics|YM2612|keyboard|FM Towns homebrew|exe|toolchain_adapter
amiga_1200|Commodore|32-bit computer|1992|68020|AGA|Paula|mouse/joystick|vbcc / vasm|adf|toolchain_adapter
amiga_cd32|Commodore|32-bit CD console|1993|68020|AGA|Paula|CD32 pad|vbcc / vasm|iso|toolchain_adapter
atari_falcon|Atari|32-bit computer|1992|68030|VIDEL|DSP56001|mouse/joystick|m68k GCC|prg|toolchain_adapter
atari_jaguar|Atari|64-bit marketed console|1993|68000/TOM/JERRY|Object Processor|JERRY DSP|pad|JagStudio|jag|toolchain_adapter
philips_cdi|Philips|multimedia console|1991|68070|CD-i video|ADPCM|remote|CD-i SDK|iso|licensed_sdk
3do|The 3DO Company|32-bit console|1993|ARM60|CEL|DSP|pad|3DO homebrew SDK|iso|toolchain_adapter
sega_cd|Sega|16-bit CD add-on|1991|68000|Genesis VDP|CD PCM|Genesis pad|SGDK + Sega CD SDK|iso|toolchain_adapter
sega_32x|Sega|32-bit add-on|1994|dual SH-2|32X framebuffer|PWM|Genesis pad|marsdev|32x|toolchain_adapter
pc_engine_cd|NEC|CD add-on|1988|HuC6280|PCE VDC|CD-DA|pad|HuC / pceas|cue|toolchain_adapter
pc_fx|NEC|32-bit CD console|1994|V810|HuC6273|ADPCM|pad|PC-FX SDK|iso|toolchain_adapter
neo_geo_cd|SNK|16-bit CD console|1994|68000|Neo Geo sprite|YM2610|pad|NGDEVKIT CD|iso|toolchain_adapter
sega_naomi|Sega|arcade board|1998|SH-4|PowerVR2|AICA|arcade I/O|KallistiOS / Naomi SDK|bin|toolchain_adapter
sega_atom_iswave|Sammy|arcade SH-4 board|2003|SH-4|PowerVR2|AICA|arcade I/O|KallistiOS homebrew|bin|toolchain_adapter
nintendo_dsi|Nintendo|dual-screen DSi|2008|ARM9 / ARM7|DSi display|DSi audio|touch/buttons|devkitARM libnds|nds|toolchain_adapter
nintendo_2ds|Nintendo|3DS family|2013|ARM11|PICA200|DSP|touch/circle|devkitARM libctru|3dsx|toolchain_adapter
new_nintendo_3ds|Nintendo|enhanced 3DS|2014|ARM11 enhanced|PICA200|DSP|touch/circle|devkitARM libctru|3dsx|toolchain_adapter
nintendo_switch_lite|Nintendo|Switch handheld|2019|Tegra X1|Maxwell|audio|Joy-Con built-in|devkitA64 libnx|nro|toolchain_adapter
nintendo_switch_oled|Nintendo|Switch OLED revision|2021|Tegra X1|Maxwell|audio|Joy-Con|devkitA64 libnx|nro|toolchain_adapter
nintendo_switch_2|Nintendo|hybrid 9th generation|2025|custom Nvidia ARM|Nvidia GPU|system audio|Joy-Con 2|licensed dev SDK|nso|licensed_sdk
psp_go|Sony PlayStation|PSP revision|2009|Allegrex|GU|PSP audio|sliding controls|PSPSDK|pbp|toolchain_adapter
psp_street|Sony PlayStation|PSP revision|2011|Allegrex|GU|PSP audio|buttons|PSPSDK|pbp|toolchain_adapter
ps_vita_tv|Sony PlayStation|Vita TV|2013|Cortex-A9|SGX543|Vita audio|DualShock|VitaSDK|vpk|toolchain_adapter
ps4_pro|Sony PlayStation|8th gen PS4 Pro|2016|x86-64|GCN enhanced|PS4 audio|DualShock 4|Sony licensed SDK|pkg|licensed_sdk
ps5_pro|Sony PlayStation|9th gen PS5 Pro|2024|x86-64|enhanced RDNA GPU|Tempest|DualSense|Sony licensed SDK|pkg|licensed_sdk
xbox_one_s|Microsoft Xbox|8th gen Xbox One S|2016|x86-64|GCN|Xbox audio|Xbox pad|Microsoft GDKX|xvc|licensed_sdk
xbox_one_x|Microsoft Xbox|8th gen Xbox One X|2017|x86-64|GCN enhanced|Xbox audio|Xbox pad|Microsoft GDKX|xvc|licensed_sdk
xbox_series_s|Microsoft Xbox|9th gen Series S|2020|x86-64|RDNA 2|Spatial Audio|Xbox pad|Microsoft GDKX|xvc|licensed_sdk
xbox_series_x|Microsoft Xbox|9th gen Series X|2020|x86-64|RDNA 2|Spatial Audio|Xbox pad|Microsoft GDKX|xvc|licensed_sdk
windows_31|Microsoft|Windows 3.x|1992|x86|Win16 GDI|WaveOut|keyboard|OpenWatcom Win16|exe|toolchain_adapter
windows_98|Microsoft|Win9x|1998|x86|DirectDraw / GDI|DirectSound|keyboard|MinGW / OpenWatcom|exe|toolchain_adapter
windows_me|Microsoft|Win9x|2000|x86|GDI / DirectX|DirectSound|keyboard|OpenWatcom|exe|toolchain_adapter
windows_2000|Microsoft|WinNT|2000|x86|GDI / DirectX|DirectSound|keyboard|MSVC Win32|exe|toolchain_adapter
windows_vista|Microsoft|WinNT|2007|x86-64|D3D10|WASAPI|keyboard|MSVC / Windows SDK|exe|toolchain_adapter
windows_7|Microsoft|WinNT|2009|x86-64|D3D11|WASAPI|XInput|MSVC / Windows SDK|exe|toolchain_adapter
windows_8|Microsoft|WinNT|2012|x86-64|D3D11|WASAPI|XInput|MSVC / Windows SDK|exe|toolchain_adapter
windows_10|Microsoft|modern WinNT|2015|x86-64|D3D12|WASAPI|XInput|MSVC / SDL2|exe|native_source
windows_11|Microsoft|modern WinNT|2021|x86-64 / ARM64|D3D12|WASAPI|XInput|MSVC / SDL2|exe|native_source
windows_arm64|Microsoft|modern WinNT ARM|2020|ARM64|D3D12|WASAPI|gamepad|MSVC ARM64|exe|native_source
windows_xp_x64|Microsoft|WinNT 64-bit|2005|x86-64|D3D9|DirectSound|DirectInput|MSVC legacy|exe|toolchain_adapter
dos_cga|IBM PC compatible|early PC CGA|1981|8088 / 8086|CGA mode 4|PC speaker|keyboard|OpenWatcom 16-bit|exe|toolchain_adapter
dos_ega|IBM PC compatible|DOS EGA|1984|286|EGA mode 0Dh|PC speaker|keyboard|OpenWatcom 16-bit|exe|toolchain_adapter
dos_vesa|IBM PC compatible|DOS VESA|1990|386|VESA VBE|Sound Blaster|keyboard|DJGPP|exe|toolchain_adapter
os2_warp|IBM|OS/2|1994|x86|Presentation Manager|MMPM|keyboard|OpenWatcom OS/2|exe|toolchain_adapter
reactos|ReactOS|Win32 compatible OS|1998|x86-64|GDI / DirectX subset|WinMM|keyboard|MinGW Win32|exe|toolchain_adapter
freebsd_amd64|FreeBSD|modern Unix desktop|2026|x86-64|SDL2/OpenGL|OSS|keyboard/gamepad|Clang/CMake SDL2|elf|native_source
freebsd_arm64|FreeBSD|modern Unix ARM|2026|ARM64|SDL2/OpenGL|OSS|keyboard/gamepad|Clang/CMake SDL2|elf|native_source
openbsd_amd64|OpenBSD|Unix desktop|2026|x86-64|SDL2/OpenGL|sndio|keyboard/gamepad|Clang/CMake SDL2|elf|native_source
netbsd_amd64|NetBSD|Unix desktop|2026|x86-64|SDL2/OpenGL|audio|keyboard/gamepad|Clang/CMake SDL2|elf|native_source
linux_arm64|Linux|modern ARM desktop|2026|ARM64|SDL2/Vulkan|PipeWire|keyboard/gamepad|GCC/CMake SDL2|elf|native_source
linux_riscv64|Linux|RISC-V desktop|2026|RV64|SDL2/Vulkan|PipeWire|keyboard/gamepad|GCC/CMake SDL2|elf|native_source
linux_x86_32|Linux|legacy PC desktop|2000|i686|SDL2/OpenGL|ALSA|keyboard|GCC/CMake SDL2|elf|native_source
raspberry_pi_4|Raspberry Pi|ARM single board computer|2019|Cortex-A72|VideoCore VI|ALSA|USB controller|GCC SDL2|elf|native_source
raspberry_pi_5|Raspberry Pi|ARM single board computer|2023|Cortex-A76|VideoCore VII|ALSA|USB controller|GCC SDL2|elf|native_source
chromeos_x86|Google|ChromeOS desktop|2026|x86-64|Linux OpenGL via Crostini|audio|gamepad|Linux container SDL2|elf|native_source
chromeos_arm|Google|ChromeOS ARM|2026|ARM64|Linux GPU compatibility|audio|gamepad|Linux container SDL2|elf|native_source
mac_os_9|Apple Mac|Classic Mac OS|1999|PowerPC|QuickDraw|Sound Manager|ADB|CodeWarrior|app|toolchain_adapter
mac_os_x_powerpc|Apple Mac|Mac OS X PPC|2001|PowerPC G3/G4|Quartz|CoreAudio|HID|legacy Xcode|app|toolchain_adapter
macos_intel|Apple Mac|modern Mac Intel|2026|x86-64|Metal/OpenGL|CoreAudio|HID|Xcode CMake SDL2|app|native_source
macos_apple_silicon|Apple Mac|modern Mac ARM|2026|ARM64|Metal|CoreAudio|HID|Xcode CMake SDL2|app|native_source
android_arm64|Android|mobile ARM|2026|ARM64|Vulkan/OpenGL ES|AAudio|touch/controller|Android NDK SDL2|apk|toolchain_adapter
android_x86_64|Android|Android emulator ABI|2026|x86-64|Vulkan/OpenGL ES|AAudio|touch|Android NDK SDL2|apk|toolchain_adapter
android_tv|Android|TV console-like device|2026|ARM64|Vulkan/OpenGL ES|AAudio|TV remote/controller|Android NDK SDL2|apk|toolchain_adapter
ios_iphone|Apple iOS|mobile touchscreen|2026|ARM64|Metal|CoreAudio|touch/controller|Xcode SDL2 iOS|ipa|toolchain_adapter
ipados|Apple iPadOS|tablet|2026|ARM64|Metal|CoreAudio|touch/controller|Xcode SDL2 iOS|ipa|toolchain_adapter
tvos|Apple tvOS|TV console-like device|2026|ARM64|Metal|CoreAudio|Siri Remote/gamepad|Xcode tvOS|ipa|toolchain_adapter
visionos|Apple visionOS|spatial device|2026|ARM64|RealityKit/Metal|spatial audio|spatial input|Xcode visionOS|ipa|toolchain_adapter
steam_machine|Valve|SteamOS PC console|2026|x86-64|Vulkan|PipeWire|Steam Input|Linux CMake SDL2|elf|native_source
asus_rog_ally|ASUS|Windows handheld PC|2023|x86-64|RDNA|WASAPI|gamepad|Windows SDL2|exe|native_source
lenovo_legion_go|Lenovo|Windows handheld PC|2023|x86-64|RDNA|WASAPI|gamepad|Windows SDL2|exe|native_source
msi_claw|MSI|Windows handheld PC|2024|x86-64|Intel Arc|WASAPI|gamepad|Windows SDL2|exe|native_source
gpd_win|GPD|Windows handheld PC|2016|x86-64|integrated GPU|WASAPI|gamepad|Windows SDL2|exe|native_source
"""
def supplemental_targets()->tuple[SupplementalHardware,...]:
    rows=[]
    seen=set()
    for n,line in enumerate(_ROWS.splitlines(),1):
        line=line.strip()
        if not line:continue
        parts=line.split("|")
        if len(parts)!=11:
            raise RuntimeError(f"hardware registry field mismatch on row {n}")
        target_id,family,generation,year,cpu,graphics,sound,controls,toolchain,output,status=parts
        if target_id in seen:
            raise RuntimeError("duplicate supplemental hardware identity")
        if not target_id.replace("_","").isalnum() or status not in (
            "toolchain_adapter","licensed_sdk","historical_reference","native_source"
        ):
            raise RuntimeError("invalid supplemental hardware spec")
        seen.add(target_id)
        rows.append(SupplementalHardware(target_id,family,generation,int(year),
             cpu,graphics,sound,controls,toolchain,output,status))
    return tuple(rows)

SUPPLEMENTAL_TARGETS=supplemental_targets()
