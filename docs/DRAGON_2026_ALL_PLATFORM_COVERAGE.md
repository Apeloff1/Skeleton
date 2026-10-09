# Dragon Native Forge: Comprehensive hardware support audit (9 October 2026)

## Scope and limitations

The game academy previously mapped **47** major platform targets and implemented
**19 original native source backends**. This change adds 122 concrete historic,
consumer, handheld, computer OS/ABI and modern mobile targets, bringing the
curated inventory to **169 distinct target identities**. It additionally implements
five independent legacy native backends plus 21 ABI-aware desktop variants, bringing source production to **55/169**.

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
| Original native source | Per-hardware implementation and build recipe exist | 50 targets |
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

## Consumer-grade and alternative-ABI PC integration

The desktop ABI layer adds 21 genuine PC-class C99/SDL2 source project
profiles without duplicating the game's gameplay mechanics. It covers
Linux ARM64, RISC-V and i686; FreeBSD x86/ARM64, OpenBSD and NetBSD;
Apple Silicon and Intel macOS; Windows 10, Windows 11 and Windows ARM64;
Raspberry Pi 4/5 ARM64; ChromeOS Linux containers; SteamOS-style x86 PC
consoles; and the Windows handheld gamepad platforms GPD Win, MSI Claw,
ASUS ROG Ally and Lenovo Legion Go.

Each source archive includes an exact OS and CPU architecture contract,
native SDL2 controller assumptions, an isolated machine-readable ABI
intent, and a CMake configure-time check that fails for wrong-system and
wrong-architecture builds. This *does not* certify a Windows ARM64,
BSD, RISC-V, Raspberry Pi or macOS Intel binary has actually compiled or
been executed; CI must provision those runners and collect true binary
format/architecture and controller performance evidence.

A CMake game source targeting ChromeOS here means the documented Linux
Crostini container, not a ChromeOS signed native app. Gaming handheld
input/battery/display certification is future work.

### Revised source coverage

169 cataloged platform identities; **50 native source generators**
(19 prior + 5 new original legacy SDK backends + 21 PC ABI-targeted
source builds); **114** without an implemented native source producer.
The expanded denominator makes percentage-based readiness
**55/169 = 26.6% for source generation only**, not a gameplay or overall
application completion estimate. No platform is awarded a compiled or
hardware-verified status from source generation.

## Open devkitPro GameCube, Wii and Nintendo 3DS production backends

Three additional original native source emitters bring the complete
source-level catalog to **55/169 = 32.5%** with **114** source-adapter
gaps. These are distinct hardware programs:

- GameCube: PowerPC Gekko libogc game using VIDEO_Init, framebuffer
  allocation, XFB console output, PAD D-pad/Start/A input, deterministic
  3-enemy pursuit, lives, invulnerability, crystal gathering, leveling,
  and a libogc/devkitPPC Makefile targeting actual DOL format.
- Wii: PowerPC Broadway/libogc program with its own wii_rules source
  configuration, Wii Remote WPAD buttons and HOME, optional GameCube
  PAD controller, XFB video synchronization, and the same original
  deterministic game rules. The runtime does not substitute HTML/SDL.
- Nintendo 3DS: ARM11 devkitARM/libctru/citro2d native game that draws
  directly on the top screen using real GPU C2D rectangle commands.
  The lower display shows status and receives native stylus input
  projected to the top game viewport. D-pad motion, four pursuers,
  score, lives, damage invulnerability and level advancement operate
  in the original C game loop.

SDK references reviewed against current publicly available
devkitPro examples. Source/build receipts are only source-level;
platform toolchains, output `.dol` / `.3dsx` bytes, 3DS emulator
GPU calls, Wii Remote and GameCube controller behavior on hardware
are not yet certified. Do not reclassify these as compiled or
emulator-proven merely because the generator produces project files.

Cross compiler gated tests run automatically only where devkitPPC /
devkitARM, libogc/libctru/citro2d and the required packaging tools
are installed. The test suite also checks that arbitrary genres
(e.g. grand_strategy) fail instead of mapping every genre label to
the same arcade collector. Detailed future work includes real SDK
build runners, emulator replay recordings, latency measurements,
sound playback and art beyond the intentionally simple original
homebrew visuals.

## New Dreamcast and PlayStation 2 source engines

The source registry increases to **55/169 targets (32.5%)** with
**114 targets still lacking native source producers**. Two newly
original 3D-era C games add the following:

**Sega Dreamcast / SH-4 / KallistiOS:** The game is written for
the KOS RGB565 framebuffer, reads an actual Maple connected gamepad
(D-pad, analog, A, Start), synthesizes original pixel art in video
memory, tracks five hit points, invulnerability, four opponents,
crystal scoring and accelerating stage pressure. Its SDK Makefile
targets a Dreamcast ELF executable. A real disc-bootable CDI is not
produced by source generation, nor is physical controller/frame
timing/audio certification implied. KallistiOS should be installed
separately. The source is original and contains no Dreamcast BIOS.

**Sony PlayStation 2 / MIPS Emotion Engine / PS2SDK + gsKit:** The
C source uses PS2 SIF RPC controller access with the 256-byte
64-byte-aligned pad buffer, native DualShock 2 controls and
Graphics Synthesizer primitive rectangles submitted via gsKit and
DMA Kit. The original game has four pursuing adversaries, collectible
objectives, health, damage protection and reset. The PS2SDK Makefile
targets a MIPS EE ELF, not a purported game disc nor copyrighted
commercial or proprietary SDK contents.

The exact target ABI and SDK must compile those sources, and PCSX2,
Flycast or physical consoles must replay input, graphics, audio,
save-state and timing scenarios before the next assurance tier
is granted. Tests assert the real native API calls, authentic source
format, limited supported genre (arcade) and deterministic
source generation. SDK-dependent compilation is attempted only
if the corresponding open source SDK/toolchain is installed.

SDK references:
- KallistiOS controller: https://kos-docs.dreamcast.wiki/group__controller.html
- KallistiOS video: https://kos-docs.dreamcast.wiki/group__video__fb.html
- PS2SDK libpad: https://github.com/ps2dev/ps2sdk
- gsKit Graphics Synthesizer: https://github.com/ps2dev/gsKit

## Additional real 8-bit computer sources

Five further original game backends increase source-target coverage to
**55 of 169 named platforms (32.5%)**, leaving **114** without an
implemented native source generator.

The new machines are Commodore VIC-20 (cc65 6502, native VIC-I
registers and 20-column display), Commodore 128 (cc65 8502 40-column
VIC-II and SID registers), Atari 400/800 (cc65 6502 ANTIC/GTIA
shadow color and POKEY registers), MSX1 (z88dk Z80 BIOS text
interface), and Amstrad CPC (z88dk Z80 firmware color/text).

The games provide actual W/A/S/D keyboard control, deterministic
enemy pursuit, gem collection, damage invulnerability, hit points,
level escalation, reset and live rendering. These are original
software designs and include platform-relevant memory-mapped
hardware controls, not ROM renamings or game-genre-only labels.

The C compiler targets are exactly `vic20`, `c128` and `atari`.
The z88dk SDK targets are `+msx` and `+cpc`. The Amstrad/MSX
source packaging uses an explicit intermediate binary intent rather
than falsely declaring a runnable disk/tape/ROM ready for users.

In `dragon-platform-coverage.yml`, cc65 is installed and the
8-bit test invokes the C compiler for those three machines.
The z88dk cross-compilation tests run only when its legitimate
toolchain is installed. An actual program binary build needs
independent emulator and controller testing before the game is
accepted as playable on the intended original computer. The
VIC-20 unexpanded memory limit is particularly important and
must be checked on the exact software/CRT target.

No copyrighted commercial games, source copies, proprietary SDKs,
boot firmware, encryption keys or unlicensed disc assets are included.

Compiler references:
- cc65 compiler and targets: https://cc65.github.io/doc/cc65.html
- cc65 supported 8-bit conio interfaces: https://cc65.github.io/doc/library.html
- z88dk conio library: https://www.z88dk.org/wiki/doku.php?id=library:conio

## Distinct NES NROM original side-scrolling cartridge engine

The **NES now has two genuine separate gameplay modes**:
`arcade_score_attack` and `side_scrolling_platformer`. The latter
is **original 6502 source**, not an alias to the earlier collector.
It creates a **vertical-mirrored iNES NROM-256 cartridge** using
two hardware nametables, a fixed 64×30-tile original stage background,
genuine 2bpp dragon and enemy sprites, real NMI OAM DMA, hardware
horizontal scroll, native controller D-pad and A jumping, grounded
gravity/ledge collision, moving enemy with damage cooldown,
four-stage goal advancement and score tracking.

The new `dragon_nes_platformer.py` owns its own 6502 game loop and
asset encoding; the build's `nes.cfg` explicitly places its 2 KiB
map section into PRG ROM. It does not reuse the arcade NES
CHR-enrichment injection path. Its real ROM build step in the
Dragon Native ROM workflow runs:
`python -m skeleton.ai.webcrawler.dragon_native_cli --target nes
 --style side_scrolling_platformer --out /tmp/dragon-nes-platform --compile`.
The test inspects iNES header bits, expected PRG/CHR capacity,
source-mode separation and native hardware register calls.
Results remain **unverified until exact-head CI** completes,
and no emulator or hardware certification is inferred.

This increases *genre/kernel depth*, not the source-target count:
still **55 of 169** platform identities with source emitters.
