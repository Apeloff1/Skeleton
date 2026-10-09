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

## VIC-20 unexpanded memory fix after real compiler evidence

The first cc65-based VIC-20 program **failed to link**, because the full
C/conio startup and rendering exceeded the original unexpanded memory
layout. The repaired implementation deliberately **does not request RAM
expansion**. It compiles 6502 assembly with ca65/ld65, links a BASIC
`SYS 4109` load/start program at $1001, stores game state below $1D00,
uses KERNAL GETIN, writes directly to VIC-I screen RAM at $1E00,
and touches the VIC-I border/sound registers at $900F/$900E.
Gameplay retains W/A/S/D controls, star collection, moving foe,
five hit points, retry and exit. The linker bounds code below
$1C00, with no C runtime. Exact-heading CI still must prove
compiler success and then emulator playback on a genuine unexpanded
VIC-20. The source-target count remains 55.

## Original Playdate and Arduboy tiny-handheld games

Two more independent hardware-native generators expand source coverage to
**57/169 identified targets (33.7%)**; 112 identified targets still do
not have source emitters. These numbers measure source implementation,
NOT verified compile, emulator or physical gameplay.

**Playdate (Panic, STM32F7)**: new native C/Playdate API project includes
its original seeded collect/chase action loop, D-pad movement, A dash,
B restart, a mechanical crank that accumulates dash charge, 400x240
one-bit rendering, score, hearts and increasing enemy pressure.
Generated build uses the installed Playdate SDK CMake integration and
Playdate's native C update callback. Source/pdxinfo is original. The
resulting .pdx (simulator) and ARM device compilation are deliberately
not asserted without an SDK and verified compile.

**Arduboy (ATmega32u4 AVR)**: native C++ Arduboy2/PlatformIO project
has a fixed-resource 128x64 1-bit OLED game with original 7-pixel sprites,
six-button input, A evasive frames, B reset, pickups, health and
progressive enemy chase. It uses no heap allocation in the gameplay
source and targets the real PlatformIO `arduboy` board. AVR flash/RAM
figures in the source audit are conservative until an actual .map or
compiler size report establishes the usage of the output HEX.

The full game builder now recognizes these projects through its native
target registry and generator, and refuses to map unsupported genres to
a falsely functional port. The separate tests inspect C API calls,
controller logic, deterministic sources and output files. Vendor-SDK
compiler tests are opt-in and cannot certify hardware without device
execution evidence.

**Sources used for API contracts:**
- Playdate C build: https://sdk.play.date/3.1.0/Inside%20Playdate%20with%20C.html
- Arduboy2 API: https://github.com/MLXXXp/Arduboy2
- PlatformIO Arduboy board: https://docs.platformio.org/en/latest/boards/atmelavr/arduboy.html

**Source coverage revised:** 57/169; missing native source: 112.

## Compatibility-aware homebrew build destinations: 11 exact-ABI revisions

The source generator also now supports **11 explicit hardware revisions**
where an existing source project can legitimately use the same native
CPU execution model and build format, but must not claim that the parent
device's emulator/binary checks certify the destination.

- GB Pocket and GB Light (monochrome DMG RGBDS, including scrolling);
- GBA Micro and Game Boy Player (GBA ARM7 cartridge, no DMG fallback);
- PSP Go and PSP Street (PSPSDK Allegrex EBOOT, differing firmware/storage);
- Nintendo DSi (Nintendo DS compatibility mode only, not DSi-only APIs);
- Nintendo 2DS and New 3DS (existing libctru 3DSX source in compatible mode);
- Atari 130XE (compatible Atari 8-bit XEX, no XE bank enhancements);
- Sega Mark III (compatible Z80/Sega VDP SMS source, accessory/ROM format review).

The new **dragon_compatible_revisions.py** checks matching parent and
destination output types, generates the actual parent native project and
preserves all original source bytes. The destination receives a separate
original source-parent hash, explicit runtime mode and limits, and
per-device compiler/emulator/hardware verification flags left FALSE.
An existing parent hardware-budget report is preserved as a
**parent-only** report rather than transplanted as a device certificate.
Other machines such as CD32, Sega 32X, FDS, Switch Lite, PS5 Pro and
Plus/4 cannot be falsely mapped to an incompatible source engine.

**Revised hardware source access: 68/169 (40.2%)**, specifically
**57 direct native source targets + 11 compatible hardware variants**.
**101 cataloged identities lack source-capable build destinations.**
Distinct engine count has NOT increased from compatibility mappings.
No device-level execution or user-facing commercial game readiness
is claimed for any of the mapped revisions.


## Verified-compiler priority: PET, Plus/4, BBC Micro and Oric Atmos

Four more source-native game projects use cc65's *documented, supported*
6502 machine targets: pet, plus4, bbc and atmos. This is intentionally
not a renamed Apple II executable. Each project compiles the same original
turn-based maze rules against its destination's actual conio text-video
and keyboard runtime, with target-specific compiler, color/no-color
constraints, output extension and memory budget. Gameplay features:

- Original bounded 28x17 maze with two rows of obstacles and a central
  wall, and routes through deliberate gaps.
- Player WASD movement with in-bounds wall rejection; collectible crystal,
  locked exit, level transition, health refill on victory.
- Deterministic turn-based pursuer AI that changes its cadence as levels
  increase, health, damage guard windows, defeat and restart.
- PET monochrome guard: color routines are excluded from compiled PET
  source; other VDU systems may use their target's supported colors.

There is **no bundled machine ROM, firmware, copied game asset or
proprietary loader**. BBC Micro and Oric Atmos use raw target-linker
output (bin); neither is falsely described as a complete SSD/TAP disk
image. The Plus/4 and PET generate cc65 PRG programs, not emulators.
Every source archive includes a Makefile with a real cc65 target choice.

The all-platform CI installs cc65 and invokes actual cl65 native targets
for all four additional computer games, checking the output file bytes.
A compiled linker output is a narrower claim than emulator, audio,
controller or physical-device verification. Audio chips are identified
in the catalog but these four programs currently implement text display
and keyboard only.

**Latest scoped registry: 169 named targets, 72 source-capable targets,
97 without source.** Exactly 11 of the source-capable targets are
explicit ABI-compatible *revisions* of previously implemented platforms;
they are not counted as 11 distinct new engines. Prior snapshot figures
in sections above (48/169, 57/169, 68/169) describe the historical
growth of this branch and should not be used as its current count.

Authoritative compiler target references:
https://cc65.github.io/doc/cc65.html
https://cc65.github.io/doc/pet.html
https://cc65.github.io/doc/plus4.html
https://cc65.github.io/doc/atmos.html
https://cc65.github.io/doc/bbc.html


### Compiler-readiness finding (Ubuntu cc65)

The Ubuntu-packaged cc65 runtime includes pet.lib, plus4.lib and atmos.lib,
but this runner does not contain bbc.lib even though cc65 recognizes the
BBC compiler target. The dedicated test therefore requires a real native
6502 object compile for BBC, marks the missing linker stage SKIPPED, and
does not claim a BBC binary exists until a full toolchain is provisioned.
PET, Plus/4 and Atmos are independently linked in the same compiler gate.
No counted source target is automatically promoted to emulator-verified.


## Original 6502 executable custody and build reproducibility

The dedicated compiler-release tool emits a *real* cc65 target-linker
artifact (not a renamed source file) for each of PET, Plus/4 and Oric
Atmos wherever its platform-specific runtime library is installed. For
BBC Micro on the current Ubuntu cc65 distribution, which lacks bbc.lib,
it emits a native machine-specific object and accurately reports
native_6502_object_compiled_unlinked. It must never say this is a working
BBC binary. If a later runner provides the proper BBC runtime, the same
command can produce the completed target linker output.

Command for a host with installed cc65:
python -m skeleton.ai.webcrawler.dragon_cc65_release --out ./generated-6502

The command requires an empty destination, only compiles the four
explicit target IDs, bounds per-process execution, reads target-specific
source directly from the original Dragon renderer, validates output size
and retains the *exact generated source* beside each output. Each
source-bound receipt includes target ID, compile/link assurance stage,
file size and SHA-256, source SHA-256, full generated source project
fingerprint, compiler signature fingerprint and missing-SDK information.
The deterministically packaged archive contains per-target original
source, Makefile, native output and receipt plus an aggregate manifest.
The CI uploads the evidence only after checks pass.

The receipt deliberately sets emulator_verified, device_verified and
filesystem_container_verified to false. A 6502 object or a cc65 linked
program does **not** certify lawful loader availability, packaging as
commercial disk/tape media, sound, scanline behavior, latency, controller
handling or game enjoyment.

No platform identity, file extension, or reused source compatibility
automatically upgrades the proof stage. This is concrete compilation
and artifact custody for four previously unsupported home computers,
while the global ledger still reads 72/169 source-capable targets.
