# Dragon Native Forge: Comprehensive hardware support audit (9 October 2026)

## Scope and limitations

The game academy previously mapped **47** major platform targets and implemented
**19 original native source backends**. This change adds 122 concrete historic,
consumer, handheld, computer OS/ABI and modern mobile targets, bringing the
curated inventory to **169 distinct target identities**. It additionally implements
five independent native source backends, bringing source production to **24/169**.

This is not every model or board ever manufactured, and 169 catalog entries
do NOT mean 169 working console games. No compiler/emulator or device test is
inferred by an item's presence in the catalog. Historical hardware that cannot
execute cartridge software (notably the 1972 Magnavox Odyssey) is marked
historical_reference, not falsely marked native-source ready.

## What the user can access now

The React Native Jeeves Dragon workshop searches and virtualizes all 169
hardware identities on consumer-grade phones. It no longer silently clips the
incoming target list to 100 entries. The default lists genuine source producers;
the All Platforms option shows adapter-needed, SDK-license-gated and historical
reference targets, with nonworking Build buttons disabled. The API exposes
a digest-bound coverage report and a specific next engineering gate for every
listed system.

## Exact implementation stages

| Gate | Meaning | What this change demonstrates |
| --- | --- | --- |
| Hardware identified | CPU/graphics/sound/inputs/SDK/ABI recorded | 169 targets |
| Original native source | Per-hardware implementation and build recipe exist | 24 targets |
| Compiler passed | Exact source built by target-specific toolchain | Not inferred |
| Emulator passed | Repeated native input, video, audio and state trace | Not inferred |
| Physical device passed | Hardware-verified timing and controls | Not inferred |
| Distribution approved | Legal access, signing and packaging | Not inferred |

A generated ROM-like filename or a PC program renamed for a console is
never accepted as a working native target.

## Original native additions

- Atari VCS / 2600 — 6507 assembly, TIA scanline kernel, WSYNC,
  RIOT joystick input, original sprite, rising score and restart.
  DASM 4 KiB cartridge intended output. Cycle-accurate scanline proof pending.
- Apple II — real cc65 6502 / ProDOS conio game, keyboard actions,
  collectibles, increasing difficulty and HP. Real cc65 native build test
  in the dedicated coverage CI. A ProDOS-loadable executable is not a
  fabricated disk image.
- Sinclair ZX Spectrum 48K — z88dk Z80, keyboard/console original
  collector, health, score and progression. Builds as Spectrum TAP with
  the separately installed z88dk cross compiler.
- Early PC 8086 DOS — OpenWatcom 16-bit real-mode console action game,
  pursuer movement, HP, collecting, replay and keyboard input. Not a
  Win32 or modern DOS extender program.
- Windows 95 — separate Win32/GDI 32-bit window procedure with real
  WM_PAINT rendering, WM_TIMER updates, keyboard controls, collision,
  pickups, HP, restart and native .exe target. Passing a modern i686
  compiler alone would not certify Win95 runtime compatibility.

All five contain independently implemented gameplay and platform build files.
They are not browser or HTML demos, nor are they already compiled ROMs.

## Expanded families and historical coverage

- 1970s/1980s: Odyssey, Channel F, RCA Studio II, Vectrex,
  Atari 2600/5200/7800, SG-1000/Mark III, NES/FDS.
- 8-bit computers: ZX81, Spectrum/Next, Apple II/IIGS,
  Commodore PET/VIC-20/64/128/Plus4, Atari 8-bit/XE,
  MSX variants, BBC Micro, Electron, Amstrad CPC, TRS-80,
  Oric, PC-88 and TI 99/4A.
- 16/32-bit and CD: PC Engine/TurboGrafx and CD, Genesis and
  Sega CD/32X, SNES, Neo Geo/CD, WonderSwan/Color, Amiga 500/1200/CD32,
  Atari ST/Falcon/Jaguar, Sega Saturn, 3DO, Philips CD-i, PS1,
  Nintendo 64, Dreamcast, Sega Naomi and Atomiswave, PS2,
  GameCube and original Xbox.
- Handhelds: Game Boy revisions and GBA, Neo Geo Pocket,
  Virtual Boy, GP32/GP2X/Dingoo, N-Gage, PSP revisions,
  Nintendo DS/DSi/2DS/3DS/New 3DS, Vita/TV,
  Playdate, Arduboy, Thumby, Analogue Pocket and Evercade.
- Modern consoles: Wii/Wii U, Switch/Lite/OLED/Switch 2,
  PS3/4/4 Pro/5/5 Pro, Xbox 360/One/S/X/Series S/X.
- PCs: DOS 8086/CGA/EGA/VGA/VESA, Windows 3.x through 11 and ARM64,
  OS/2, classic Mac OS, PowerPC Mac OS X, Intel/Apple Silicon macOS,
  Linux x86/ARM64/RISC-V, Steam Deck/SteamOS, FreeBSD ARM/x86,
  NetBSD/OpenBSD, ChromeOS, Raspberry Pi, gaming handheld PCs.
- Mobile/TV: Android ARM64/x86/TV, iPhone/iPadOS, tvOS, visionOS.

Hardware revisions and OS/ABI variants are identified separately where
their controllers, packaging, certification or runtime compatibility differ.
This is not a claim that each needs a distinct codebase, nor that the
same PC binary has been tested on every revision.

## Exact gaps and engineering roadmap

The dragon_platform_readiness module exposes 145 missing source adapters
with SDK, target identity, classification and next required work. Priority
should go to independently compiled and emulated native ports: Apple II,
Spectrum, Atari, 8086 DOS and Win95 first; Dreamcast KallistiOS, PS2SDK,
GameCube/Wii libogc, Nintendo 3DS libctru, VitaSDK, Switch libnx and
8-bit MSX/CPC next. Modern PC variants should use shared engine source
with genuine target-architecture build and controller tests. Android/iOS
require real NDK/Xcode app packaging, permissions and signing. Licensed
PS/Xbox/Nintendo releases remain blocked without legitimate developer SDK
authorization. No proprietary system firmware, ROMs, game assets, DRM keys
or unlicensed SDKs are included.

CI: dragon-platform-coverage.yml validates all 169 target records, 24
source generators, disallowed target/style pairs, and performs a genuine
Apple II cc65 build. Other cross compilers are tested if they are installed.
CI only proves outcomes of checks that actually pass on the exact head.

## Toolchain documentation

- z88dk: https://z88dk.org/site/gettingstarted
- cc65: https://cc65.github.io/doc/cc65.html
- cc65 Apple II: https://cc65.github.io/doc/apple2.html
- OpenWatcom: https://openwatcom.org
- DASM: https://github.com/dasm-assembler/dasm
