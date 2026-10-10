# Cross-era homebrew platform registry and port planning

**Owner:** `skeleton/ai/game_builder` (canonical AI-native game builder).
**Status:** candidate platform coverage and deterministic port blueprints, **not** native game compilation, tooling certification, or release approval.

## Why discontinued and obscure platforms matter

Every catalogued system can be selected as a **creative basis**, as a **destination for a porting plan**, or both. Production discontinuation is *not* a reason to drop it. PC, game console, handheld, arcade board, calculator, mobile runtime, toy and hobbyist microcontroller histories all contain valuable gameplay and interaction designs.

The maintained registry currently includes 524 entries and 30 approximate capability presets; this is an **interim curation corpus**, not a complete worldwide platform census. It deliberately tracks the unusual, regional, transitional and failed commercial systems alongside mainstream machines. Examples: Fairchild Channel F, Interton VC 4000, Super Cassette Vision, Watara Supervision, Gamate, Mega Duck, WonderSwan and SwanCrystal, Neo Geo Pocket, PC-FX, FM Towns Marty, CD-i, CD32, Pippin, Nuon, Jaguar CD, Gizmondo, Tapwave Zodiac, Atari ST, RISC OS, ZX80/81, Thomson MO5, MSX, PC-88/98, X68000, Sega Model 2/3 arcade, Konami GX, Sega NAOMI, TI/HP calculators, Palm OS, BREW, J2ME, Arduboy and RP2040.

The UI-neutral selector in `editor_platforms.py` exposes every catalogued system as browsable source/destination options, with search, family/type filters and a full target-directed design graph. It never presents an unverified native exporter as available. Connect the selector through the product API and actual editor surface in a subsequent integration step.

The approximate tier and preset are **planning heuristics**, not machine-specific hardware specifications, verified instruction sets, video timings, RAM addresses or supported executable targets. Individual regional models, hardware revisions, add-ons, controllers, multiformat media and FPGA reimplementations need machine-specific adapters and test evidence.

## Separate legal cross-reference for machine-bound games

The published legal-source matrix and executable rights classifier are documented in [the homebrew and spiritual-successor legal cross-reference](GAME_BUILDER_LEGAL_CROSSREFERENCE.md). Hardware exclusivity of a third-party commercial game does not automatically grant a copyright monopoly over its underlying mechanics or genre. It **does** leave its protected expression, code, branding, sound, maps, software license and console technical-measure rules intact. Researching a platform's architecture or building an independent game does not itself require rights to that commercial game; commercial distribution and console access are independently gated.

`legal_census.catalog_rights_census()` builds a policy review card for **every curated hardware record**. It reports catalogued systems with missing actual per-target SDK licence review, lack of individual legal release certification, potential TPM restrictions, and hardware/driver acceptance requirements. It does not assign unverified legal statuses as "approved" merely because a historical console is abandoned.

## Source and destination are separate

A historical game design **basis** is not a permission to copy the original game's ROM, art, soundtrack, script, trademark or characters. Port planning accepts only an original/cleared homebrew project with a stable rights-evidence reference. User-provided SHA-256 is an *assertion/reference*, not proof of independent verification.

Every platform is a candidate for source or destination **planning**. Only an independently qualified adapter can turn a blueprint into a real output format. The current registry marks **every toolchain unverified**; there are zero verified game binaries, builds, or releases implied by this change.

Source systems that are difficult to target directly may still serve as inspiration for original mechanics and aesthetics while shipping to an accessible destination. Do not infer that emulation or porting justifies proprietary BIOS, firmware, decryption keys, SDK redistribution or a commercial game rip.

## Modes

| Mode | Direction | Design rule |
| --- | --- | --- |
| `faithful` | Any -> any | Preserve original game loop, identity, visual language; adapt controls, storage, audio and rendering |
| `enhanced` | Usually old -> modern | Increase animation, lighting, fidelity, simulation, accessibility and controls **without** losing the original style |
| `reverse_constrained` | Modern -> earlier hardware | Quantize/retarget tiles, sprites, palette, sound channels, world scale, performance and inputs |
| `cross_hybrid` | Two cleared homebrews -> any | Combine authorized mechanics, transform expressive assets and give the result an independently authored identity |

Portability is a directed **planning graph**. The same source project may have multiple independent target blueprints, each with its own constraints and digest. `compile_port_route` is a multi-destination fan-out from the original platform, **not** a verified multi-hop build chain. Multi-target planning is not evidence that an intermediate port exists. A true build pipeline must hand each verified artifact to the next independently qualified target adapter.

## Example

    from skeleton.ai.game_builder.platform_registry import default_registry
    from skeleton.ai.game_builder.port_planner import (
        HomebrewSource, PortMode, PortRequest, compile_port, compile_port_route
    )

    registry = default_registry()
    print(registry.summary())

    owned = HomebrewSource(
        project_id="my-original-game",
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256="a" * 64,  # replace with genuine, independently reviewed evidence
        creative_identity=("tactical turn sequence", "ink outlines", "short rounds"),
    )
    design = compile_port(PortRequest((owned,), "windows_modern", PortMode.ENHANCED))
    assert design.planning_status == "design_only_toolchain_unverified"
    assert not design.releasable

    variations = compile_port_route(owned, (
        "windows_modern", "sega_dreamcast", "nec_pc_fx", "arduboy",
    ))


## First implemented native-source adapter: desktop SDL2

The original, deterministically solvable `PlayableWorld` can now produce an **actual C11 SDL2 game source project**, independently of HTML: `desktop_native_export.compile_native_desktop(world, homebrew_rights, target_platform_id, authorized=True)`. The supported source-project targets are `windows_modern`, `linux_desktop` and `macos_modern`.

The artifact includes working map, collectibles, hazards, health, level transitions, win/loss, keyboard and gamepad movement, a basic animated pixel renderer, CMake, and a manifest containing the world, replay and rights-evidence hashes. `export_native_desktop_source` writes a new standalone source directory; it neither installs dependencies nor runs arbitrary commands. SDL2 development libraries and a C compiler are required to build; hardware-dependent native binaries are **not built or verified by this PR**. Title strings and map rows are escaped into C literals. The exporter rejects a non-matching project ID, unsupported console targets, absent authorization and unverified gameplay worlds.

A typical desktop build, after selecting the platform's legal SDL2 toolchain:

    cmake -S generated-project -B build
    cmake --build build --config Release

On Windows, the resulting artifact can be a genuine `.exe`; its actual runtime behavior, SDL2 distribution, installer creation and signing still require target-specific CI and hardware testing. This route deliberately does **not** masquerade as a Game Boy / PlayStation / Xbox exporter.

## Native executable build-and-replay acceptance pipeline (October 2026)

This branch additionally introduces `.github/workflows/game-builder-native-desktop.yml`. Its three operating-system jobs use **real host compilers and native SDL2 development libraries** to build the generated C11 source, then invoke `skeleton_homebrew --verify-replay` (or `skeleton_homebrew.exe --verify-replay` on Windows). The C implementation embeds the generated world's deterministic safe actions for every level and checks map transitions, collectible scoring, health, action count and victory. Native ELF, Mach-O and PE headers are independently checked by `scripts/game_builder/native_desktop_ci.py`, which also records SHA-256 of each compiled executable.

The matrix targets Linux x86-64, macOS arm64/Intel depending on the selected runner, and Windows UCRT64 x86-64. Sparse checkout avoids unrelated historic filenames on Windows. GitHub Actions artifacts contain the actual native binary, source-project manifest, runtime DLL on Windows and run evidence. **Run conclusions must be checked on the current commit SHA** before treating these as compiled or gameplay-verified. Adding a CI workflow does not, by itself, attest that a build has passed.

This acceptance checks one deterministic, independently generated original three-level game, not every authored homebrew project, physical console or hardware revision. It does **not** provide console ROM output, prove every game works, confer third-party rights, sign an installer, or qualify redistribution of SDL2 runtime dependencies. The emitted project's own manifest remains fail-closed with `executable_built=false`, `native_headless_replay_executed=false` and `releasable=false` until actual separate build/QA/release receipts exist.

## Build adapter qualification still required

1. Confirm **independent homebrew source authority** through the existing game-builder rights ledger, source inventory, license/attribution rules and legal review where needed.
2. Register an **appropriately licensed/redistributable SDK or open toolchain** for that exact platform and hardware revision, plus reproducible tool versions, build environments and target ABI.
3. Implement/export the real format: ROM, optical-disc image, cassette/disk executable, arcade board image, native installer/package or firmware, as appropriate. No HTML-only substitution for native console outputs.
4. Verify frame pacing, video mode, memory and VRAM budgets, palette behavior, audio channels, input mapping, save compatibility, accessibility, reliability and original-game replay.
5. Validate on legal emulator configurations and, where possible, representative physical hardware. Where native toolchains are infeasible, document the limitation and produce **design-only** output rather than claiming support.
6. Bind each passing gate to independently inspectable receipts; only then may a separate release pipeline certify the adapter and artifact.

## Coverage expansion policy

A platform record must have a stable identifier, historically reasonable name/family, interaction/render profile, explicit catalog maturity and test coverage. **Do not invent machines merely to reach a quota.** Distinguish a real standalone platform from a software peripheral, an arcade board family, a configuration or a secondary display accessory. Confirm historical details and local toolchain availability before promoting records to hardware-verified status.

Licensing and trademark policy is fail-closed. "Clone", hybridization and decompilation do not waive copyright, trade secret, access-control, trademark, privacy or contractual obligations. Original gameplay concepts may inspire wholly new homebrew, but copied distinctive expression and misleading branding require review. Successful compilation is not legal clearance.

## Regressions and integration

- `skeleton/testing/test_game_builder_platform_porting.py` tests catalog breadth, data validation, missing targets, rights rejection, determinism, retro-to-modern feature expansion, modern-to-retro demotion, hybrid behavior and multi-destination planning.
- `platform_catalog.json` is included in the installed Python package data.
- `platform_registry.py` and `port_planner.py` are canonical AI-native modules, not mirrored legacy forge code.
- This increment adds **design/inventory capability**; future increments must supply compiler adapters, tested toolchains, genuine game content generation, real target packages and independently signed builds.


## Archival evolution corpus: the missing long tail

The hardware catalog now includes first-generation fixed-game Pong-style consoles and regional models, portable variants and peripherals, 8-bit regional computers, Japanese microcomputers, classic workstations, modern devices, and arcade board generations. None of this implies exact game cartridge interchangeability or executable support.

The separate `evolution_lineages.json` records **94 dated design milestones across 26 reference lineages**. It is a bounded *illustrative design-succession DAG*, not a proof of backwards compatibility. `evolution_archive.py` rejects unknown machines, duplicate identifiers, reversed chronological parent edges and fictitious source verification. Its report lists all curated platforms currently missing timeline and lineage records. `evolution_practice.py` turns any authorized dated progression into a set of generated, deterministic **playable original puzzle worlds** with reproducible winning replays. Exercises are target-inspired, not native builds for those consoles.

An operator can inspect all gaps without a database or network:

    python -m skeleton.ai.game_builder.archive_cli summary
    python -m skeleton.ai.game_builder.archive_cli lineage nintendo_famicom nintendo_switch

## Long-tail archival discovery: offline MAME metadata importer

Current MAME documents tens of thousands of machines, many of which are not distinct game consoles: some are ROM-set variants, arcade boards, chips, computer configurations, gambling devices, BIOS parents, or clone entries. Bulk copying their names into the console registry would be dishonest and technologically useless.

`archive_import.py` reads an official **locally supplied** `mame -listxml` snapshot using a streaming parser with size, XML-entity and record-count defenses. It extracts machine identifiers, titles, dates (where parseable), manufacturers, clone relationships, display/input descriptions and emulator-driver status. It does not copy ROM entries, proprietary software, BIOS, checksums or game assets into the curated record. Each resulting row is a *candidate* requiring separate system-type, hardware revision, rights and primary-source review.

Example (the reader does not download or run anything):

    mame -listxml > mame-listxml.xml
    python -m skeleton.ai.game_builder.archive_cli import-mame mame-listxml.xml --review-file missing_platforms.jsonl

**Candidate `mame -listxml` entries are not a production target and are never automatically promoted.** Running the optional archive import requires the user to provide a legally obtained local metadata file. It does not authorize use of third-party ROM sets.

### Closure audit

A global archival completeness percentage **cannot** be claimed while the worldwide historical platform denominator is undefined, machine revisions and rebrands are inconsistently counted, and individual record-level historical sources are still missing. The `archive_coverage_report()` intentionally reports the concrete known gaps and a `complete_historical_census: false` gate. Treat that boolean as a hard stop for claims of comprehensive archive completion.

Future archival closure is by tracked evidence, not arbitrary line or platform quotas: identify primary sources and dated hardware revisions, reconcile manufacturer/region/rebrand/board-family identities, ingest external metadata as candidate records, separate peripherals and software environments from independent systems, verify machine-specific constraints with lawful source references, implement real native homebrew toolchains, and validate against representative hardware.

The exact-head `Homebrew Historical Archive` GitHub Action checks the maintained catalog, lineage validation, rights-safe MAME metadata ingest and generated evolution-game replay regressions. Passing the Action means these **code contracts** passed, not that every historical machine is known.


## Foundational games before the home console

The archive now extends to **1931** for early pinball and to **1947** for the cathode-ray tube amusement-device patent. It also catalogues Ferranti Nimrod, EDSAC, a Tennis for Two analog apparatus, PDP-1/PDP-8 computing contexts, Computer Space, Galaxy Game, Atari arcade Pong, and analog/electro-mechanical arcade hardware including Periscope, Rifleman, Sea Raider, and other pre-video experiences.

Preserve these distinctions:

- `mechanical` = physical balls, playfields, levers, springs and friction; output is a simulation or independently qualified mechanical build, not a console ROM.
- `electromechanical` = motorized illusions, lamps, mirrors, reels and sound mechanisms with their own timing, safety and maintenance.
- `precursor` = patents, one-off experimental computers, installations, or analog apparatus, potentially never sold or broadly reproducible. A patent concept is not a shipping machine.
- `arcade`, `computer`, `console` and `handheld` continue to mean different hardware/media and input arrangements. Historical inspiration does not imply artifact-format compatibility.

The timeline uses **candidate years**, not independently confirmed primary-source dates. Its `predecessor` edges denote curated design succession, not binary lineage; no arbitrary cross-vendor ancestry is fabricated.

Historical reading material for review includes [Brookhaven National Laboratory's early game history](https://www.bnl.gov/about/history/firstvideo.php), [MAME's machine-history introduction](https://docs.mamedev.org/initialsetup/mameintro.html), [MAME's historical layouts](https://docs.mamedev.org/techspecs/layout_files.html), [Wikimedia Commons' generational gallery](https://commons.wikimedia.org/wiki/Home_game_consoles_by_generation) and the [Video Game History Foundation research library](https://library.gamehistory.org/). These are references for future item-by-item audits, **not blanket provenance attestations**.

Even after this expansion, full worldwide hardware/clone/revision coverage, machine-specific verified graphics/audio limits, and native homebrew executable support are substantially incomplete.


## Native original console engines: genuine Game Boy and NES cartridge source

The platform registry and evolution-games plane now have **two independent,
world-derived console assemblers**, not just porting advice or a reskinned
desktop game. Both consume the exact validated `PlayableWorld`, preserve its
cryptographic digest and safe-winning replay, use procedurally authored original
2bpp pixel art, and emit compiler-ready source projects without copying any
commercial cartridge content.

| Stage target | Source producer | Native binary format | Toolchain | Gameplay implemented |
| --- | --- | --- | --- | --- |
| Game Boy DMG | `game_boy_native_export.py` | `.gb` ROM-only cartridge | RGBDS 1.0 (`rgbasm`, `rgblink`, `rgbfix`) | Hardware LCD/VRAM/OAM, 32-column tilemap, D-pad, walls, crystals, hazards, health, multi-level victory |
| NES / Famicom | `nes_native_export.py` | iNES NROM-256 Mapper 0 `.nes` | cc65 (`ca65`, `ld65`) | 6502, PPU nametable and 2bpp CHR, sprite DMA, controller, walls, crystals, hazards, health, multi-level victory |

These are **actual console-specific machine-code source projects**. They
are not HTML exports, emulator applications, JavaScript wrappers or general
C files renamed to game-console extensions. Both use their corresponding
machine architecture and graphics-memory layout. Console artwork is original.

The Game Boy adapter bounds the playable source grid to **19×17 tiles** and
uses a 32×18 tilemap. The NES adapter bounds source levels to **31×29 tiles**
and maintains a 32×30 CPU-RAM-backed PPU nametable. Overflow is rejected,
not silently truncated into an unplayable cartridge. Compiling a game
does not establish frame-perfect emulation, physical-console qualification,
third-party distribution permissions, or runtime replay certification.

CI jobs:
- `Game Builder Native DMG ROM`: installs RGBDS, generates a deterministic
  original three-stage game, assembles/links `.gb`, checks cartridge size,
  entry point, Nintendo-defined hardware header and checksum, and records SHA-256.
- `Game Builder Native NES ROM`: uses real cc65, emits a three-level
  original NROM cartridge, checks complete PRG/CHR layout, Mapper 0,
  reset vector, original generated tile data and SHA-256.
- `Game Builder Native Desktop Executable`: builds genuine SDL2/C11
  native game executables on Windows, macOS and Linux, then runs the embedded
  three-level deterministic gameplay replay on each native host.

**Important:** Above are validation *steps to run*, not passing-certification
claims for any unchecked Git commit. The ROM workflows do not currently
provide complete emulator-controlled gameplay playback; release
certification remains independently gated. Source manifests deliberately
continue to say `rom_compiled=false` or `cartridge_built=false`, because
a generated project is not itself a compiled and verified ROM.

### Evolution-game bridge: history lessons become native original games

`evolution_native_sources.py` now consumes the playable per-era
`EvolutionPracticePack` and materializes real stage-specific sources:
authentic Game Boy ROM projects, NES ROM projects and SDL2 desktop games
where the stage hardware permits it. Every other archival system remains
an explicit `design_only` stage. A historical practice map that exceeds a
console's display envelope becomes `budget_incompatible`, not a fake game
or silently clipped level. Each stage retains its source-world digest,
winning-gameplay-replay digest, authorship reference, target and build
qualification status.

This is the executable bridge between the dated game history archive,
the platform selector, the playable-world engine, the rights-gated
porting system and actual native-machine game sources. New archive
entries cannot inflate the count of qualified native backends.


## Executable homebrew upgrades: Commodore 64 and emulated Game Boy gameplay

A further native adapter, `c64_native_export.py`, now emits **original
Commodore 64 6510 programs** rather than NES binaries repackaged for 8-bit
computers. Its hardware backend directly addresses the VIC-II 40×25 text
screen, color RAM, CIA joystick port 2, raster register and SID sound
registers. Every generated maze tile, starting location, item, hazard and
exit comes from the verified independently authored game world. Levels,
health, scoring, input-driven movement and original synthesized sound
are runtime mechanics, not static design annotations.

`Game Builder Native C64 PRG` runs the actual cc65 C64 compiler/linker
against the source project, checks the $0801 load address, BASIC SYS
launcher and output hash, and stores the loadable `.prg` as a GitHub
artifact. As with other targets, a passing compilation is **not**
a claim that VICE emulation, physical 6510 hardware or distribution
approval has passed.

For the Game Boy DMG backend, the new
`game_boy_memory_replay.py` builds a per-input independent reference
from the original generated maze and winning route. The
`scripts/game_builder/emulate_game_boy_ci.py` tool is designed
to run the actual assembled cartridge inside PyBoy, press and release
each D-pad input, and compare real emulated WRAM bytes for player
coordinates, current level, health, crystal count, score, win and loss.
It reads real linker-produced symbols rather than guessing absolute
WRAM addresses. Any divergent controller response, wrong level
transition, phantom victory or missing collectible makes the gate fail.
The underlying authoring manifest cannot mark emulator verification
passed merely by having supplied a reference trace.

The editor/export selector now distinguishes **six candidate native-source
destinations** (three desktop SDL2 targets, original Game Boy ROM,
original NES ROM, and original C64 PRG). Everything else in the
historical catalogue remains a design/planning target until a
machine-specific compiler adapter and acceptance process are implemented.
The existing archive and original-game rights controls apply to
these additions. Neither platform inspiration nor a binary header
constitutes a right to redistribute copyrighted commercial games.

## Historical DOS 8086 native game architecture

The builder has a seventh genuine, original native-source target:
`dos_native_export.py` targets a **real Intel 8086-compatible DOS .COM
program** and produces NASM `bits 16`/origin `0100h` source, not a
desktop emulator, HTML page, renamed EXE or hypothetical port plan.

The engine is independently adapted to IBM PC-compatible hardware conventions:
text mode 3 via BIOS interrupt 10h, genuine segment-addressed text video
memory at B800:0000, keyboard scan codes through BIOS interrupt 16h,
native real-mode CPU instructions, and DOS interrupt 21h for clean exit.
Runtime logic tracks all authored level maps separately from immutable
level source data, applies wall collisions, collectible clearing,
health and hazard damage, retains progression through all stages,
and displays a changing level/GEMS/HP/score HUD. It uses original
ASCII/text-mode aesthetics, preserves the world digest and reference-winning
route, and emits a reproducible `Makefile` invoking real NASM.

`Game Builder Native DOS 8086 COM` assembles the actual `.com` file
and checks its startup instruction bytes, BIOS and DOS calls,
video-memory setup, bounded image size and SHA-256. Emulator execution
and physical hardware are independent follow-up gates, not implied by
successful compilation or a valid DOS program signature.

The public `native_game_cli.py` and historical
`native_evolution_cli.py` now include DOS-native source output,
and `editor_platforms.py` identifies the
`nasm_8086_pc_textmode_com_source` capability. Thus the seven
available native-source destinations currently cover three modern
desktop operating systems, two different classic cartridge formats,
Commodore 64 and 8086 DOS. The broader archive still remains research/
design-only wherever a true machine-specific backend is absent.

## Original Atari 8-bit game programs: authentic 6502 / ANTIC / GTIA / POKEY

The builder now includes `atari8_native_export.py`, a separate genuine
Atari 400/800 **48KB-class** native source adapter. It translates the
original, independently solvable maze world into a DOS-loadable `.xex`
project built by `cl65 -t atari`. It uses the Atari OS 40-column
text display through cc65 `conio`, the real STICK0 joystick shadow
at $0278, ANTIC's VCOUNT ($D40B) as the frame clock, Atari colour
shadows, and original POKEY audio on $D200/$D201. The produced game
has interactive movement, all separate original levels, collectible
clearing, hazard damage, health, scoring and victory conditions.
It uses no Atari commercial-game ROMs or artwork.

`Game Builder Native Atari 8-bit XEX` compiles an actual 6502
executable with cc65 on an Ubuntu runner and checks the Atari segmented
load format, valid segment address bounds, RUNAD autostart and source
hash before uploading the binary as a downloadable workflow artifact.
This is a *compilation-level* control: passing such a gate does not
imply full Atari OS emulation, physical hardware verification, or
rights to redistribute material that was not independently authored.

This specific program envelope assumes a compatible Atari 8-bit
OS installation and adequate RAM. The early 16KB Atari 400 cannot
be treated as equivalent to a later 48KB configuration without a
separate real memory-budget pass. The larger family of 5200, XE,
XEGS and compatible Atari machines remains catalogued but is
not fraudulently counted as additional independently certified
game exporters.

**Source-engine progress**: three desktop builds plus separate
Game Boy, NES, Commodore 64, IBM DOS 8086 and Atari 400/800
native-source adapters. These are eight authored targets, not
eight legally approved commercial cartridge reissues.

## Game Boy Color — real hardware-accelerated authored RGB555 port

The dedicated `game_boy_color_native_export.py` compiles a different native
hardware target from the monochrome Game Boy: **CGB-only** RGBDS assembly with
an authentic cartridge flag `$0143=$C0`, independently authored 15-bit
RGB555 art palettes, FF68/FF69 background palette memory, FF6A/FF6B sprite
palette memory, FF4F VRAM bank selection, and 576 background-map color
attributes per stage stored in video RAM bank 1. Bank 0 is restored before
the monochrome-compatible deterministic collision/gameplay engine reads tile
data. None of this relies on downloaded Nintendo game characters, textures,
commercial ROMs, or firmware images.

Unlike a static screen-color filter, the native CGB program colors floor,
walls, collectible gems, hazards, and exits independently using five distinct
background palettes. The original sprite palette is also initialized in
the physical CGB OBJ palette memory. Real RGBDS builds use `rgbfix -C`;
the color-only flag is checked in the compiled cartridge header rather than
being inferred from the filename.

The standalone `Game Builder Native Game Boy Color ROM` workflow builds
an actual CGB-only cartridge, runs its authored gameplay in **true PyBoy
Game Boy Color mode**, checks linker-symbol-bound guest WRAM on every D-pad
move, and uploads the source/ROM/symbols/CPU evidence. A source project
does not claim that cartridge compilation, emulator execution, a physical
Game Boy Color test, or distribution rights were automatically approved.

The standalone homebrew editor, command-line game creation pipeline and
historical Game & Watch → Game Boy → Game Boy Color evolution exporter now
support **nine native-source targets**, including both separately playable
handheld generations. Unsupported systems remain explicit design-only
candidates rather than fake binary output.

## Apple II+/IIe native original homebrew games

`apple2_native_export.py` generates genuinely new **Apple II 6502**
games using the Apple II-specific cc65 runtime, not a Windows game
masquerading as an Apple program. The interactive engine targets genuine
40×24 text hardware through the Apple II conio driver, waits on the
Apple II keyboard through `cgetc()`, recognizes I/J/K/L and W/A/S/D
for original maze movement, and synthesizes short original sound events
by toggling the genuine Apple II $C030 speaker soft-switch. Its tilemaps,
positions, scoring, damage, health, unique game progression and victory
come directly from a solved, individually authored `PlayableWorld`.
The 6502 program is compiled using `cl65 -t apple2` into the native
**AppleSingle** file format used for DOS 3.3/ProDOS transfers.

The `Game Builder Native Apple II 6502` workflow builds an actual
AppleSingle native executable, validates the format/header version,
bounded data-fork entries and SHA-256, and runs source authority tests.
This is **not** an automated Apple II disk-image boot, AppleWin emulator
playthrough or physical-machine certification, and it does not bundle
Apple system ROMs or third-party DOS 3.3 disks.

Compatibility applies to an Apple II+/IIe style machine with a
compatible cc65 runtime and Language Card configuration; the original
unexpanded 1977 integer-BASIC Apple II is *not automatically certified*
by this backend. More recent Apple IIGS and other Apple systems remain
distinct research/port candidates until their own acceptance gates pass.

The platform editor, public rights-bound CLI and game evolution compiler
now expose **ten native source destinations**. The archive of 524
candidate historical systems continues to distinguish native code
generation from independent emulation and release rights.

## One-command original game portfolio — every implemented machine

The portfolio builder, `native_portfolio_cli.py`, produces the *same*
source-authored, provably winnable homebrew game for every implemented
machine target, with each port assembled as a **separate real source
project**. It is not a collection of falsely renamed executables or HTML
renderings. For example:

```bash
python -m skeleton.ai.game_builder.native_portfolio_cli \
  --basis bandai_wonderswan --project-id star-voyage \
  --title 'Original Star Voyage' --seed 1986 \
  --rights-evidence ./my-original-work.txt \
  --identity 'original constellation puzzles' \
  --identity 'own distinctive artwork' \
  --out ./all-original-native-ports \
  --authorize-original-homebrew
```

The command creates machine-specific source subdirectories for the genuine
Game Boy, Game Boy Color, NES/Famicom, Commodore 64, Atari 400/800, IBM DOS
8086, Apple II, Windows, Linux, and macOS engines. Every target manifest
is checked against the **same game-world digest**, winning-replay digest,
author-supplied evidence hash and exact source-content digest.

The all-platform source portfolio is constructed in a temporary sibling
folder and atomically promoted to the requested **new, non-overwritten
destination** only after every requested machine has succeeded. Any target
with an incompatible hardware constraint aborts and removes staging output.
The resulting `portfolio-manifest.json` uses relative source paths and
a reproducible cryptographic digest, independent of the destination folder
name. A subset may be selected with repeated `--target` options.

`Game Builder All-Native Homebrew Portfolio` performs a real full-port
generation in GitHub CI and uploads the resultant hardware-specific
source projects for download. This is original **source export**: it
does not falsely certify compiled ROMs, executable installation, emulator
runs, original hardware, independent copyright clearance, or release
approval. Those remain separately measured acceptance gates, and copied
third-party game assets continue to be refused.

## Authentic Sinclair ZX Spectrum 48K game and tape export

`spectrum_native_export.py` is a new independent Z80 backend for
original ZX Spectrum 48K games. It does not claim the 128K, +2, +3
or other clones are independently certified hardware just because they
share a Z80 CPU. The source uses the actual Spectrum ROM character
output entry `RST $10`, ROM screen-clear routine, and the physical
**ULA keyboard-row matrix ports** ($FBFE, $FDFE; W/A/S/D movement and
Q exit). Native gameplay includes real Z80 grid bounds checks,
original per-stage room maps, gems, scoring, hazards, health,
terminal victory, 50Hz frame timing via `HALT`, and ULA
border/beeper feedback through port $FE.

The Z80 assembler builds a load-address-$8000 code binary.
`spectrum_tap.py` packages the resulting bytes as a **real Spectrum
CODE tape image**, with the genuine 19-byte CODE header block,
flag parity, native-load address, code block, checksum and strict
byte-for-byte verification against the compiled binary. Both the
assembler and packer run entirely offline. The export includes its
own packer source, Makefile, README, machine-specific assembly and
original rights-bound manifest; it distributes **no Sinclair ROM**.

The `.tap` is deliberately a CODE-only image, not a fictional
autostart cartridge. On a legally provisioned 48K Spectrum-compatible
machine or emulator, follow these BASIC commands and load the tape:

```basic
CLEAR 32767
LOAD "" CODE
RANDOMIZE USR 32768
```

`Game Builder Native ZX Spectrum 48K Tape` assembles a real Z80
binary via `z80asm`, creates genuine .tap records, validates original
binary parity and supported hardware budget, and uploads the playable
game for independent loading and evaluation. A successful compilation
or tape header does **not** automatically prove emulator gameplay,
real-machine testing, ownership of third-party assets, or release
approval. Those remain separate evidence gates.

With this backend the source exporter spans **11 independently
implemented native target destinations** across historical computers,
console cartridges and modern desktop systems. The historical
catalogue retains design-only entries until their own hardware-specific
code generators and independently verified format controls exist.

## MSX1 Z80 native cartridge — actual BIOS VDP, joystick, sound and RAM

The new `msx1_native_export.py` independently compiles original authored
games to the **MSX1 Z80 16KB page-1 cartridge** format, not a ZX Spectrum
tape renamed `.rom`. An authentic cartridge begins with the `AB` header
and executes its original INIT routine inside address range $4000–$7FFF.
It uses real MSX1 BIOS interfaces: INITXT ($006C) configures the 40x24
VDP text display; CHPUT ($00A2), POSIT ($00C6) and CLS ($00C3) draw the
original tile map and score; CHSNS ($009C) and CHGET ($009F) acquire
keyboard input without blocking joystick polling; GTSTCK ($00D5) reads
joystick 1; BEEP ($00C0) synthesizes original hardware output. A bounded
page-3 RAM scratch region at $C000/$C100 holds mutable game state and
prevents accidental writes to ROM.

The native game includes a full playable original story of discrete maze
levels, interactive keyboard/joystick movement, collisions, collectibles,
hazard damage, health, four-digit score, victory/restart and 50/60 Hz
interrupt-frame timing. No MSX BIOS, commercial cartridge assets,
modified third-party game ROM, or copyrighted example binaries are included.

`msx1_rom.py` wraps the assembled Z80 source into a deterministic
**16KB .rom** with verified AB header, zeroed unused hooks, in-page
INIT address, actual BIOS CALL opcodes, original source signature,
deterministic FF padding and a byte-for-byte match with the Z80 assembler
output. The native MSX1 GitHub workflow compiles the ROM with `z80asm`,
checks the genuine machine format, runs original rights and hardware-budget
regressions, and uploads source and compiled artifacts.

Neither the source-export stage nor ROM validation automatically asserts
the game passed an MSX1 CPU emulator, ran on actual hardware, or has been
approved for distribution by third-party rightsholders. Those are separate
verification obligations. MSX2, MSX2+ and turbo R remain **distinct hardware
design targets**, not additional independently qualified native exporters.

The editor-facing real source reachability inventory and transactional
all-platform original-homebrew portfolio now include **12 separate native
machine targets**. Candidate historical hardware remains represented,
without inventing code generators for systems that are not implemented.

## Original Sega Master System console ROM — authored 4bpp tiles and real VDP

The separately implemented `sms_native_export.py` produces **actual Z80
machine code** for a genuine export Sega Master System 32KB ROM. It is
not a Game Gear binary, a JavaScript emulation wrapper, an MSX BIOS
program or a relabeled source collection. Unlike the MSX it directly
controls the console hardware: Mode-4 VDP **$BF control/$BE data** ports,
32x24 background name-table at VRAM $3800, original 8x8 planar
**4bpp** glyph/tile patterns (floor, walls, star crystals, hazards,
exits, player, score digits and HUD labels), 32 authored RGB222
palette entries, video interrupts at Z80 vector $0038, original
SN76489 tone playback at port $7F, and native player-one controller
reads from port $DC.

The machine has only 8KB of internal RAM, so all mutable original
game state and map copies are bounded at $C000/$C100. The emulator
cannot simply load ZX Spectrum or MSX machine code and expect it to
work: this is a wholly independent low-level console engine.

The game's scored stage progression, safe-to-goal tile rules,
collectibles and hazards derive from the same independently solved
world as all the other supported machine-native builds.

The companion `sms_rom.py` takes the **actually assembled Z80 source**
and produces a 32,768-byte `.sms` cartridge with the correct
`TMR SEGA` header at offset $7FF0, export-region and 32KB-size
byte $4C, and the BIOS-required 16-bit checksum over exactly the
preceding $7FF0 bytes. It rejects invalid reset vectors, malformed
VBlank/pause-button handlers, missing VDP/PSG/joypad opcodes, altered
source bytes, duplicate overlays, and noncanonical ROM padding.

The dedicated `Game Builder Native Sega Master System ROM` workflow
assembles the actual Z80 game, validates the cartridge against its
original source and checks the hardware and game rights envelope.
Its verified binary is uploaded as a build artifact. No commercial
Sega game content, cartridge memory dump, assets or system BIOS is
bundled. Real emulator gameplay and hardware tests are separately
required before declaring the binary fully accepted or suitable for
distribution.

The portable editor also exposes a distinct **Game Gear source**
backend using SDCC and devkitSMS's Game Gear-specific video/input
envelope. Game Gear is **not** counted as having a verified compiled
binary merely because a Master System cartridge compiles, and
additional hardware distinctions remain separately enforced.

The overall editor currently exposes **14 machine-specific native
source targets** (including Game Gear's source-only stage), against
524 archived historical hardware candidates. Counts refer to source
authoring, not to independently completed hardware qualification.

## ColecoVision (1982) — real OS7/TMS9918A Z80 console cartridge

The native hardware-target catalogue now includes a genuinely distinct
**ColecoVision** engine, not a Master System Z80 binary renamed for
Coleco. `coleco_native_export.py` converts an independently generated,
solvable original game into ColecoVision Z80 assembly, and the companion
`coleco_rom.py` packages the assembled source as a 32KiB unbanked
ColecoVision `.col` cartridge.

The machine-specific program contains the actual BIOS-recognized
`55 AA` direct-boot header, seven OS7 restart callbacks, game
INIT address and VBlank NMI soft vector at cartridge address $8021.
It calls Coleco OS7 `MODE_1` and `LOAD_ASCII` BIOS routines, then
renders the original maze using the physical TMS9918A VRAM at
$1800 through VDP port $BE/control port $BF, with interrupt-synchronized
updates, a player-one joystick at port $FC selected by $C0, and
short original SN76489 PSG chimes through port $FF.

ColecoVision's memory architecture is not the Master System memory
architecture. It has only **1KiB of physical game RAM**, mirrored in
$6000–$7FFF. The game specifically places source-derived mutable world
tiles at $7000, score/health/player data at $7300, and its native Z80
stack below $73F0. Its authoring compiler rejects worlds that exceed
the 32x24 display or one-KiB memory envelope rather than moving game
state into nonexistent $C000 RAM.

The `Game Builder Native ColecoVision Z80 ROM` workflow genuinely
assembles the independent Z80 game, checks every required header and
soft vector, verifies the ROM against its original binary source, and
runs adversarial tests for hardware memory, original game rights,
forged headers and tampered code. No BIOS file, commercial cartridge
image or externally owned artwork is bundled. Importantly, completion
of this build workflow **does not** imply independent ColecoVision
emulator playthrough, original hardware qualification or commercial
distribution approval.

This increases separately implemented native machine-*source*
destinations to **15** of 524 archive candidates. The source count
must not be confused with qualified playable hardware binaries.

## ColecoVision guest-Z80 replay: real gameplay without distributing a BIOS

A second, independent `Game Builder ColecoVision Native Z80 CPU Replay`
workflow now drives every original safe-action joystick direction through
**actual compiled native Coleco cartridge Z80 instructions**, rather
than concluding that a valid header means a playable game.

`emulate_coleco_ci.py` uses the externally validated `z80-python`
instruction core and implements a strict, explicitly bounded ColecoVision
device adapter: physical **1KiB mirrored RAM** ($6000–$7FFF),
BIOS-selected boot address, BIOS-to-cartridge NMI trampoline at $0066,
TMS9918A VRAM name-table writes, register-1 video interrupt
enable/disable, active-low first controller and SN76489 sound port.
The simulator supplies exactly **two stub BIOS routines**, MODE_1 and
LOAD_ASCII, each modeled as RET. No proprietary OS7 BIOS is uploaded,
downloaded, or reverse-engineered into the project; a stub is never
described as full firmware emulation.

The original `PlayableWorld` emits a separately hashed winning
action/state reference; the CPU runner compares every actual
guest-RAM state (level, player, gems, health, game-over, score)
and the tile drawn in VRAM after every action. Any diverging
instruction, modified author-source digest, unregistered BIOS
access, unauthorized memory write, malformed VDP control latch,
or missing physical joystick poll fails closed. CI retains
the built 32KiB .col ROM and independent CPU execution receipt.

The code also explicitly disables **VDP NMI during two-byte video
name-table address writes**, then acknowledges and rearms VBlank at
the end of each redraw, avoiding a hardware race that merely
using Z80 `DI` could not prevent. This requires real Coleco NMI
semantics, not SMS maskable INT semantics.

Passing this CPU replay is evidence for native Z80 execution and
the particular audited guest device paths. It is **not** equivalent
to accurate timing/pixels for the real TMS9918A, a fully booted
proprietary Coleco OS7 BIOS, an independently tested ColecoVision
emulator, an actual original console, or legal distribution clearance.
