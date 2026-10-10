# Cross-era Native Homebrew Artifact Validation

**Goal:** Real, content-addressed game artifacts, not "HTML game" surrogates.
**Safety:** File layout and checksum validation does not prove a game boots,
does not prove originality, and does not authorize the use of commercial IP.

## Structural desktop executables

Module: `skeleton/ai/game_builder/native_binary_structure.py`

The previous native-byte gate was deliberately a weak format sanity check.
A file beginning with `MZ`, `ELF` or Mach-O magic could pass even when no
operating-system image was actually present.

A new independent structural parser inspects real file-descriptor-backed
images with bounds checked before each header or region read. The parser
examines file size, program/section table dimensions, expected architecture,
mapped code segments, execution permissions and the entrypoint relationship
to the on-disk image. It then re-hashes the complete image in small bounded
chunks **from the same verified file descriptor**. No symlink, hardlink,
directory, oversized or wrong-target native executable is accepted.

| Desktop output | Format | Strict checks |
| --- | --- | --- |
| Windows | PE32/PE32+ PE/COFF | DOS offset, PE signature, COFF machine, executable-not-DLL, bounded optional/section headers, file alignment, raw section bounds/overlap, executable entrypoint in mapped code |
| Linux | ELF32/ELF64 | Class, endianness, executable/PIE type, CPU, bounded program/section tables, loadable segment file/memory consistency, file-backed entrypoint in executable LOAD |
| macOS | thin 64-bit Mach-O | Executable CPU type, command count/size, segment bounds, 64-bit section table boundaries, LC_MAIN or native thread entry, executable segment/entry offset |

**Intentionally unsupported:** PE resource/data-directory semantic verification,
ELF extended program-header counts, 32-bit/FAT universal Mach-O files,
platform code signatures, notarization, ASLR deployment policy, dependency
runtime resolution and dynamic loader compatibility. Those need separate
dedicated assessments before hardware or publisher acceptance.

These checks are conservative; an OS can accept other uncommon variants.
Never "fix" validation by changing the output extension or forging a magic
header. Resolve the compiler, binary type and runtime compatibility instead.

`run_structurally_verified_native_release_gate()` chains:
actual native file-byte receipt, fully parsed native executable structure
and external, administrator-signed/pinned independent reviewer policy.
All three must describe the exact signed game and output bytes.

Even when a structurally well-formed PE, ELF or Mach-O passes:
`executable_boot_verified=false`,
`binary_executed_successfully=false`,
`legal_noninfringement_certified=false`, and
`release_authorized=false`.

The test fixtures emulate headers and segments. They are **NOT working games**
and must not be used to claim native runtime acceptance.

References:
- Microsoft PE/COFF: https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
- Linux ELF manual: https://man7.org/linux/man-pages/man5/elf.5.html
- Apple Darwin Mach-O header reference:
  https://github.com/apple/darwin-xnu/blob/main/EXTERNAL_HEADERS/mach-o/loader.h

## Actual retro ROM and tape formats

Module: `skeleton/ai/game_builder/native_retro_artifact.py`

Six hardware targets now have a local cartridge/tape evidence intake. Existing
native source exporters remain distinct; no commercial game binaries or
device firmware are downloaded or bundled.

| Era / platform | Verified format metadata | Not automatically verified |
| --- | --- | --- |
| Nintendo Game Boy DMG | Bank-aligned header ROM length, mapper code, header checksum, reset entry | Boot-logo redistribution rights, real LCD/input behavior |
| Game Boy Color | Color mode flag and DMG/CGB exclusivity, header checksum, ROM size | Color VRAM attributes/CPU timing or hardware |
| NES / Famicom | Strict iNES1 NROM mapper zero, PRG/CHR bank sizes, no trainer, reset vector into CPU ROM | Authentic 6502 gameplay, PPU synchronization |
| Sega Master System | Existing Sega 32 KiB TMR SEGA checksum/header, reset and interrupt vector checks | All BIOS/hardware revisions and actual sound/input |
| MSX1 | Existing 16 KiB AB page-1 cartridge validator, INIT and BIOS-call metadata | Z80 full instruction validity and all BIOS variants |
| ZX Spectrum 48K | Existing two-block TAP checksum, length, load-address and Z80 entry checks | Firmware boot, keyboard mapping, full tape playthrough |

Every inspected output must match an explicit expected **SHA-256**. A guessed
file type, corrupt ROM, modified checksum, altered target or symlinked path
fails closed. Passing metadata is not equivalent to verified game execution.

References:
- Pan Docs: https://gbdev.io/pandocs/The_Cartridge_Header.html
- iNES header format: https://www.nesdev.org/wiki/INES
- Existing project-created SMS/MSX/Spectrum format packers and native CI
  remain the source of their supported exact hardware-specific constraints.

### Rights and anti-plagiarism remain independent

Programming patterns, game rules and ideas do not by themselves determine
copyright infringement. High-level visual identity, story expression,
characters, audio, protectable maps, UI and third-party licenses still
require the separate originality/rightsholder checks.

A legitimate homebrew ROM may require boot-screen trademarks or proprietary
SDK approval for certain distribution channels. A cartridge file that has
a correct checksum cannot grant a hardware maker license.

Unresolved: direct signed evidence linking every *retro* cartridge to its
reviewed source, real emulator/hardware verified gameplay replay, region-aware
packaging, toolchain provenance and publisher approval. These remain separate
milestones, not fictional green status fields.

## CI and adversarial acceptance

`.github/workflows/game-hardware-archive.yml` now runs:
- `test_game_builder_native_binary_structure.py`: PE/ELF/Mach-O
  boundary/range mutations, valid synthetic layouts, digest and link attacks.
- `test_game_builder_strict_release_pipeline.py`: full strict desktop
  image plus independently pinned reviewer chain.
- `test_game_builder_native_retro_artifact.py`: real six-era-format
  generated bytes, copy/substitution resistance, mapper, checksum and
  loader-header mutation tests.

Do not merge until exact-head CI is green, and do not interpret focused
format tests as closure of repository-wide unrelated failing gates.


## Original NES NROM-256 reproducibility (October 10, 2026)

A dedicated **real 6502 NES cartridge** acceptance path now complements the
Sega Master System / Game Gear progression. The NROM source exporter emits
original world-specific ca65 assembly, linker configuration, NES cartridge
header and original 2bpp sprite/background artwork. The native NES workflow
uses the open-source `cc65` compiler and linker; it does not download
copyrighted commercial NES games, redistributable firmware or a proprietary SDK.

New verified-format implementation:
- `scripts/game_builder/native_nes_ci.py` reads actual ROM bytes with the
  repository's bounded, descriptor-based no-follow intake. In addition to
  mapper-zero iNES and exact 32 KiB PRG / 8 KiB CHR bank sizes, it checks
  file-backed **6502 reset, NMI and IRQ vectors**. A file with a recognizable
  `NES\x1a` prefix but invalid startup is not admitted.
- `scripts/game_builder/nes_reproducibility_ci.py` compares **two separately
  generated original source trees** and their actual independently built
  NROM cartridge bytes. It enforces four exact source files (`main.s`,
  `nes.cfg`, `Makefile`, `manifest.json`), permits a separately
  bounded compiler output directory, rejects extra/unreviewed source files
  and linked code, checks the original world/rights/safe-route identities,
  verifies both PRG and CHR regions byte for byte, and re-checks their
  SHA-256 digests after structural inspection.
- `skeleton/testing/test_game_builder_nes_reproducibility.py` attacks
  missing/modified source, proprietary extras, symlinked directories,
  swapped ROM files, iNES mapper violations, reset/interrupt vectors,
  false source rights claims, oversized native input, FIFOs, and
  checksum/ROM substitutions.
- `.github/workflows/game-builder-native-nes.yml` now actually runs
  two independent authoring exports and two native `ca65`/`ld65`
  compilations. It asserts matching ROM bytes, original-source identity,
  safe-route provenance and no unearned publication/hardware claims.
  The dedicated tests also run under `game-hardware-archive.yml`.

**Evidence boundaries:** A two-build SHA-256 match means actual inspected
binary bytes are identical; the offline verifier cannot independently attest
that two compiler processes genuinely executed. A structurally plausible
NROM with reset/NMI/IRQ code is **not** proof of a completed NES game route.
The pipeline deliberately records `emulator_gameplay_verified=false`,
`physical_hardware_verified=false`,
`third_party_rights_independently_cleared=false` and
`publication_authorized=false`. A full 6502 CPU + PPU + APU + controller
simulation, real reference-route acceptance, reproducible SDK provenance and
external copyright/license review remain distinct unfinished milestones.

A synthetic ROM in the adversarial unit tests is a **format-validation
fixture only**. The real platform workflow invokes ca65/ld65 against the
original exported assembly, independently of that fixture.


## NES native 6502 CPU, original PPU, controller and map acceptance

The NES lane now has a separate, bounded **real instruction-level execution**
gate in addition to source reproducibility and iNES ROM format validation.
It uses the open-source, BSD-3-Clause Py65 **NMOS 6502** core with a controlled
NROM memory map and observable subset of the Famicom CPU/PPU bus:

- actual 2 KiB mirrored CPU RAM and bankless $8000-$FFFF 32 KiB PRG;
- time-advanced synthetic NTSC PPU $2002 VBlank latch with read-to-clear;
- $2006/$2007 background/palette addressing and increment modes;
- authentic $4014 256-byte OAM sprite-DMA source page;
- $4016 eight-button controller latch and serial shift-register reads.

The bootstrap asserts that the actual compiled game reaches its initialized
sprite DMA after writing **all 32 PPU palette bytes** and **all 960 original
background tile bytes**, within a hard CPU-instruction budget. It does not
accept a magic-header-only synthetic ROM stub or pretend that a ROM exists
if file integrity checks fail. On the first successful native CI witness,
the original real cartridge executed **33,001 6502 instructions**, produced
**1,024 name-table writes** (960 tiles plus 64 attributes), **32 palette
writes** and one sprite DMA.

The next stage reuses the actual authored, content-addressed source folder to
derive the first independently solvable D-pad action and initial world spawn.
It advances the compiled NES CPU through the actual 4016 controller input
handler and observes the sprite location copied by the next $4014 DMA.
The first genuine ROM witness moved right from original world cell (1,1) to
(2,1), changing native sprite X **8 → 16** and making eight controller-port
reads over **41,581 total instructions**. The recorder marks the first
action verified but never claims the *entire* reference route completed.

An additional world-hash safeguard now independently encodes the original
first level's full **32 × 30 = 960 tile** name table into the source manifest.
Both the real boot and the 6502 controller runner compare the **actual
PPU-observed** name-table SHA-256 against this PlayableWorld-derived digest,
not merely the count of writes. The game generation reports the actual
first controller action, starting coordinate, expected neighboring target,
and exact 960-byte background hash in its separately compared source file.

Adversarial test suites include:
- `test_game_builder_nes_6502_boot.py` — CPU/PPU RAM mirrors, 2002 read-to-clear,
  2006/2007 palette and name-table access, OAM DMA, serial controller bits,
  instruction budget refusal and forged ROM rejection;
- `test_game_builder_nes_6502_controller.py` — original route metadata,
  source/ROM substitution, invalid direction, unsafe source symlinks and
  premature/unbounded replay claims;
- `test_game_builder_nes_native.py` — independently reconstructs the entire
  original first-stage tile-map digest from PlayableWorld rows;
- `test_game_builder_nes_reproducibility.py` — original independent
  source/ROM equality and mapper/interrupt/rights defenses.

**Scope boundaries:** Py65 is a real 6502 instruction interpreter, but
this project-owned minimal PPU/controller observer is **not** an independently
validated cycle-exact NES/Famicom PPU/APU or a reliable rendering/audio
emulator. A single world-derived controller action is not a complete
native playthrough. Physical console behavior, developer-toolchain origin,
copyright title and official publisher authorization remain unverified.
No third-party game ROMs, copyrighted commercial sprites or console firmware
are required for these original homebrew checks.

The successful native CPU/one-step observations came from prior runs; any
newer source/digest or first-stage pixel acceptance control must independently
pass its own exact-head CI before the stronger guarantee is credited.
