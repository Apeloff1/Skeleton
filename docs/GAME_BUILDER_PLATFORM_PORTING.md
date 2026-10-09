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
