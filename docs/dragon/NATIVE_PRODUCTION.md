# Dragon Native Production: governed multi-target release lane

Scope: October 2026 capability delivery on top of existing canonical owner
`skeleton/ai/webcrawler`. This document describes implemented source-release
functionality, not a claim of full engine/console readiness. Existing providers,
game builder, emulator, console SDK and runtime owners remain unchanged.

## User workflow

Inspect concrete source generator and ROM compiler coverage:

    python -m skeleton.ai.webcrawler.dragon_native_production capabilities

Plan before a single filesystem write:

    python -m skeleton.ai.webcrawler.dragon_native_production plan \
      --title "Original Lunar Wanderer" --style arcade_score_attack \
      --targets game_boy,nes,pc_linux --attest-original-rights

Produce an immutable portfolio from the existing creator CLI:

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --title "Original Lunar Wanderer" --style arcade_score_attack \
      --portfolio-targets game_boy,nes,pc_linux \
      --attest-original-rights --authorize-publication \
      --out ./dragon-releases

Audit an already-published portfolio without any network or AI dependency:

    python -m skeleton.ai.webcrawler.dragon_native_production verify \
      --out ./dragon-releases \
      --index dragon-production-<20-character-request-prefix>.json

The index filename comes from the printed build receipt. No generated game
automatically launches, uploads, publishes to a store, executes a build command,
or claims independent approval.

## Real capabilities in this batch (20 substantive delivery slices)

| # | Production capability | Actual proof / limit |
|---|---|---|
| 01 | Hardware-aware inventory of existing targets | Existing platform catalog is inspected; catalog presence is not emitter support |
| 02 | Honest emitter/SDK status | Licensed and missing emitters remain unavailable |
| 03 | Style × target capability preflight | Rejects target/genre mismatch before creating files |
| 04 | Multi-platform batch planning | Up to 16 distinct declared targets, deterministic ordering |
| 05 | Bounded request identities | Digest binds title, style, targets, seed, build mode and rights evidence |
| 06 | Original-work rights attestation | Explicit opt-in required; no automatic legal clearance asserted |
| 07 | Documentary external rights references | License/public-domain categories require a reference; still human-reviewed |
| 08 | Local compiler discovery | RGBDS/cc65 availability is checked separately from source generation |
| 09 | Native source composition | Uses existing hardware-specific emitters, not HTML wrapped as a ROM |
| 10 | Strict source-file validation | Traversal, corrupt path, binary injection and file inventory caps |
| 11 | Hardware source-budget replay | Recomputes the existing console/PC source resource auditor |
| 12 | Native mode and stage identity | Records actually emitted gameplay modes, not requested-only genre labels |
| 13 | Optional verified ROM build | Reuses bounded existing Game Boy, Game Boy Color and NES local compilers |
| 14 | Structural binary admission | Only checked ROM headers, size and digest; not emulator certification |
| 15 | Deterministic source archives | Sorted members, stable timestamps/permissions, replayable hashes |
| 16 | Per-file build provenance | Canonical source fingerprints and source hashes in the release receipt |
| 17 | Adversarial offline ZIP verification | Rejects changed members, duplicates, unsafe metadata and unknown extras |
| 18 | Resource-bounded portfolio packing | Per-file, archive, total memory and source limits |
| 19 | Atomic immutable local publication | Fsync and no-overwrite linking; identical repeated publication is idempotent |
| 20 | Aggregate offline production audit | Independent index/archive hash reconciliation and gameplay parity caveat |

These 20 slices are one cohesive **working production lane**, not 20
unrelated placeholders or 20 new processes. The implementation must pass
the focused tests and mandatory architecture gates before it is considered
landable.

## Application-native source export (additional completed integration)

The existing authenticated Dragon Academy API now includes:

- \`GET /api/dragon-academy/native/production/capabilities\` —
  truthful native source emitter matrix, available to authenticated users.
- \`POST /api/dragon-academy/native/production/source-bundle\` —
  creates a deterministic multi-platform source bundle **in memory**, returns
  a ZIP directly to an authenticated \`editor\` or \`admin\`.
  Requires separate \`approved=true\` and \`original_work_attested=true\`.
  Maximum 3 source targets, 3 MiB, no local toolchain execution, no
  publication filesystem changes, no model invocation and no background work.

Example request JSON:

\`\`\`json
{
  "title": "Original Lunar Wanderer",
  "style": "arcade_score_attack",
  "targets": ["game_boy", "nes"],
  "seed": 1,
  "rights_basis": "original_homebrew",
  "rights_reference": "",
  "original_work_attested": true,
  "approved": true
}
\`\`\`

The response is \`application/zip\` with stable nested release ZIPs,
\`production-index.json\`, a content digest header and an explicit
\`source-only-not-a-compiled-game\` claim header. The app cannot request
a ROM compiler, and viewer/dev/anonymous principals cannot obtain a new
creator source release. The existing Dragon practice progress, XP, evidence
signer and lessons are unaffected.

### Frontend creator experience

The production endpoint is now exposed in the existing Expo product application:

- Open **Product → Studio → Native homebrew**, or navigate to
  \`/dragon-native-production\`.
- Sign in as \`editor\` or \`admin\`; read-only, anonymous and development
  fallback principals cannot export.
- The screen loads the authoritative platform/style matrix. Only platforms
  with implemented source emitters are selectable; a selection is bounded
  to three targets.
- Enter the title and style, confirm original-work rights separately from
  permission to generate, then request an original source ZIP.
- The response is validated as a source-only ZIP with a bounded size before
  saving/downloading. Web uses the browser download action; Android/iOS save
  locally and use platform sharing when available.
- Neither the screen nor the backend grants compilation, rights approval,
  independently signed release evidence, or knowledge/memory promotion.

The application obtains source ZIPs on demand and does not persist a phantom
"completed ROM" or invent browser-side build history. A source bundle remains
a preliminary project artifact, not a playable certified game.

### Portable authored game design (new integrated delivery)

Both the native production engine and the authenticated Studio editor now
accept an **optional portable design**. It supplies original art direction
and executable generator parameters without touching existing game providers:

- \`palette\`: one of the known original style palettes.
- \`hero\`: hatchling, knight, explorer, pilot, astronaut or robot.
- \`quest_theme\`: original world themes including space, forest, ruins,
  clockwork, volcano, ice and crystals.
- \`difficulty\`: 1–10; \`stages\`: 1–8; \`candidates\`: 1–24.
- \`seed\`: the request's same deterministic 32-bit value across targets.
- \`project_notes\`: bounded data, never programmatic source, commands or
  authority-granting instructions.

The portfolio generator translates the same original specification into a
canonical typed \`GameDesign\` for each hardware target and feeds it to the
existing native emitter. For implemented desktop paths this influences actual
campaign and source creation. For console cartridges whose generator only
supports a single collectible-chase game, it enforces one stage/one
candidate, adjusts unsupported palette classes, and **explicitly discloses**
that hero/theme/difficulty may not be applied in the game runtime. Neither
the UI nor the receipt claims a feature-equivalent port.

A canonical \`port_plan\` accompanies every production archive with the
portable design digest, actual target design digest, production title/seed,
target constraints and adaptation list. The independent verifier
reconstructs the exact typed adaptation and, when the desktop emitter
provides \`dragon-game-design.json\`, matches it to the source-resident
design manifest. Unapproved changes to degradations or source design
invalidate verification.

The legacy source-only requests without \`portable_design\` remain supported.
No console or PC product can claim functionality it has not actually
implemented.

### Feasibility preview before resource-consuming source emission

The creator screen supports a separate **Preview hardware adaptations**
action. The authenticated \`POST /api/dragon-academy/native/production/preview\`
endpoint invokes source/target admission and the canonical typed game design
translator, returning a target-by-target feasibility decision, actual target
palette, permitted stage and candidate counts, and exact adaptation notes.
It **does not call native source emitters**, run a compiler, create files,
award rewards, or grant production approval. Rights attestation is still
explicit; pressing Preview does not substitute for the separate generation
approval. The preview is invalidated after any input change.

### Verified game evolution across successive native releases

Operator tooling supports a new offline comparison command:

\`\`\`sh
python -m skeleton.ai.webcrawler.dragon_native_production compare \
  --previous-dir ./release-v1 --previous-index dragon-production-<previous>.json \
  --current-dir ./release-v2 --current-index dragon-production-<current>.json
\`\`\`

Both input portfolios must first pass the complete source, ROM-structure
(where present), hardware-budget, index and manifest verification.
The comparison then classifies every platform as \`identical\`,
\`source_changed\`, \`binary_changed_only\`,
\`release_receipt_changed_only\`, \`target_added\` or
\`target_removed\`. It identifies changed gameplay modes, campaign counts,
portable design digests, toolchain evidence and verification levels.
The review signals distinguish source changes that call for new gameplay
testing from binary/receipt-only changes that still require new build review.

This is usable for original-game iteration and port upgrading, without
claiming that content changes are automatically improvements or that an
emulator has proved the game playable. The verifier binds both manifests'
content digests before comparing them, preventing a read-after-verification
manifest replacement from masquerading as a trustworthy diff.

### Real standalone native Linux game — compiled and exercised

Unlike the source-only cross-platform creator route, the new operator-only
\`dragon_native_desktop.py\` owner compiles an actual C99 Linux puzzle game
using the repository's existing original solver-backed Sokoban generator.

\`\`\`sh
python -m skeleton.ai.webcrawler.dragon_native_desktop build \
  --title "Original Dragon Puzzle Campaign" --seed 1977 \
  --difficulty 8 --stages 6 --attest-original-rights \
  --authorize-local-build --out ./my-original-linux-game
\`\`\`

The builder writes the approved native C sources into a temporary build tree,
invokes the allowlisted host \`cc\` compiler with fixed warning/C99 arguments,
validates the output is a genuine bounded ELF executable, **executes its
real \`--selftest\`** and requires one correct stage-completion trace per
generated level, then **executes \`--list\`** to verify level inventory.
It archives the source release ZIP, executable and runtime evidence together
under a content-addressed name.

The independent \`verify\` command replays every original Sokoban level via
the exact bounded Python BFS solver and checks source fingerprints, ELF
structure, binary hash, compile settings and runtime receipt integrity
**without executing code from a downloaded or modified archive**.
A runtime result is a report from the trusted local builder, not a
cryptographic proof of origin or safety. Restrict builders with appropriate
OS-level sandboxing; no arbitrary user-uploaded source is accepted and this
capability is never exposed to a web request or research crawler.

This is a **genuine compiled terminal game**, not a promise of a 3D
PlayStation, Nintendo, Xbox or modern PC graphical game.

### Original pixel-art forge connected to cartridge runtimes

\`dragon_native_artforge.py\` translates original protagonist and world
themes into eight 8×8 four-index sprite tiles. Distinct silhouettes are
authored for hatchling, knight, explorer, pilot, astronaut and robot,
and original collectible visuals are authored for space, ruins,
crystals, forest, clockwork, ice and volcano themes. Gameplay palettes
apply bounded color-index remappings.

The compiler emits true interleaved 2bpp Game Boy and planar 2bpp NES tiles.
The Dragon native source generator embeds these bytes directly in the
canonical \`Tiles\` / \`PlatformTiles\` / NES \`CHARS\` source sections,
preserving sprite addresses and ROM build layouts. This affects native
cartridge picture data, not just a manifest or a web preview. The art
manifest records original sprite digests and actual target source
application, and the release verifier reconstructs the original tiles
and compares them with the emitted assembly.

On the Game Boy and Game Boy Color arcade creators, actual controller
movement now selects the authored walk frame in SM83 assembly; stationary
idle/blink states select their corresponding cartridge graphics.
The NES arcade creator has equivalent 6502 movement-driven sprite index
selection and a frame-timed blink path, with dedicated zero-page state
initialized in the reset routine. These are real ROM-side animation branches,
not presentation-only UI animations or metadata claiming animation.
Structural ROM/build gates still need to compile and validate the result.

Only Game Boy, Game Boy Color and NES are claimed as integrated native
art targets here. Other target emitters retain their existing, separately
documented graphic capabilities; do not extrapolate new coverage to them.
Game Boy color indices do not mean a DMG has additional RGB colors.

### Original game series with verified stepping-stone outputs

\`dragon_native_evolution.py\` supports a bounded offline evolution series
of **2–12 source editions**, each with up to 3 native game targets (36
individual projects total). It deterministically evolves hero, palette,
world theme, difficulty, stage count, search budget and seed from one
operator-approved original design.

An episode is a real generated/archived/verified native source portfolio;
not just a task-plan entry. Each edition gets an individually verified
immutable archive and source-index. Consecutive releases are compared for
actual source/binary/receipt changes; the series index is published last.
A stopped or failed series never gets a completed-series receipt, but
previous immutable editions are safely resumable.

\`\`\`sh
python -m skeleton.ai.webcrawler.dragon_native_evolution preview \
  --title "Original Crystal Odyssey" --targets game_boy,nes \
  --portable-design ./original-design.json --attest-original-rights \
  --editions 6
python -m skeleton.ai.webcrawler.dragon_native_evolution build \
  --title "Original Crystal Odyssey" --targets game_boy,nes \
  --portable-design ./original-design.json --attest-original-rights \
  --authorize-series --editions 6 --out ./original-odyssey
\`\`\`

The design JSON is strictly validated, has canonical versioned keys and
rejects symlink input, excess bytes, duplicate keys and unknown controls.
Series verification replays the exact deterministic design variants,
inspects every target's verified source release and checks inter-edition
manifest linkage. An unchanged source graph, emulator crash or inferior
game mechanic is **not** automatically a training gain; any machine
learning/memory promotion belongs to the separate evidence and approval
planes.

### Live original-pixel-art preview in the creator screen

The authenticated application exposes
\`POST /api/dragon-academy/native/production/art-preview\`.
It returns exactly four generated 8×8 original source sprites:
actor, blink pose, world collectible and enemy. Input is a strict
allowlisted \`hero\`, \`quest_theme\`, \`palette\`, 32-bit seed and one
supported cartridge target (Game Boy, Game Boy Color or NES). The endpoint
uses the **same native original-art generator** that rewrites actual
cartridge assembler tile tables; no third-party images, copyrighted
characters, executable assets or gameplay binaries are involved.

The Expo creator shows the four sprites as pixel tiles, with actual
applied 2bpp tone choice and target noted. UI thumbnails illustrate
color-index data, not exact DMG or NES calibrated display colors.
Previews are cancellable if user controls change, and no placeholder
sprite is falsely shown when the preview endpoint is unavailable.

### Playable user-authored campaigns and verified live gameplay physics

**New native gameplay capabilities** extend the existing original C99
Sokoban editor beyond source prototypes.

- In-game H now computes the shortest **current-position** path through a
  bounded C99 BFS of player/crate states, rather than incorrectly returning
  only the starter move. It handles crate pushes, already completed stages,
  legitimate deviations and failed bounded searches. The compiled binary
  provides \`--hint-selftest\` for every actual generated level.
- \`--simulate LEVEL COMMANDS\` replays up to 400 \`wasdur\` moves with
  genuine native crate collision, undo and reset. It reports the full player,
  crate, move and push state and a deterministic FNV state digest.
- A separate Python physics interpreter independently reproduces those
  transitions. The native Linux release builder executes **four distinct
  movement traces per level**, compares every field and refuses to package
  a mismatched executable. The source-hash audit additionally regenerates
  the canonical C game and header from the original level specification.
- **Opt-in procedural stages** add bounded walls and routes to hand-authored
  original seeds. Every admitted changed map must pass the authoritative
  exact shortest-path solver. Unsupported or unsolvable variants fall
  back to clearly labeled original solutions; legacy geometry is preserved
  by default.
- **Direct original puzzle authoring** supports real 12×10 boards with
  wall \`#\`, floor \`.\`, avatar \`@\`, crate \`$\`, and goal \`o\`. The app
  has a touch-friendly multi-stage grid editor, paint tools and a separate
  Validate action. Up to eight distinct stages are checked by bounded BFS
  before their exact rows can become a compiled native game.
- Authored game boards enter both the canonical request digest and
  source-only ZIP. The standalone Linux builder accepts the same boards
  via a strict, versioned JSON file and executes their native gameplay
  tests. No HTTP route accepts executable C/source code or compiles on
  behalf of an untrusted visitor.

Author a puzzle in the creator screen under **fixed screen puzzle → Author
my own boards**, or generate a canonical starter:

\`\`\`sh
# Prepare original level pack JSON using the strict Python API.
python - <<'PY'
import json
from pathlib import Path
from skeleton.ai.webcrawler.dragon_native_puzzle_authoring import starter_authored_levels
Path("original-levels.json").write_text(json.dumps(starter_authored_levels(2), indent=2))
PY

# Build an actual standalone original C99 Linux game from that map content.
python -m skeleton.ai.webcrawler.dragon_native_desktop build \
  --title "Original Authored Puzzle Quest" \
  --authored-levels ./original-levels.json \
  --difficulty 5 --attest-original-rights \
  --authorize-local-build --out ./built-original-game

# Or generate new BFS-vetted level routes:
python -m skeleton.ai.webcrawler.dragon_native_desktop build \
  --title "Original Labyrinth" --stages 4 --difficulty 8 \
  --procedural-levels --attest-original-rights \
  --authorize-local-build --out ./original-labyrinth
\`\`\`

The level-pack JSON has exact structural fields, no scripts, no hidden
assets or external URLs, small file bounds, duplicate-level rejection,
source fingerprints and no automatic legal clearance. All C compilations
are restricted to the local operator build boundary, not Expo or the
research crawler. Real gameplay verification covers the original Sokoban
rules, not every game mechanic available in the broader multi-genre
factory.

### Native Windows x64 binary and Steam Deck Linux-target source

The original C99 puzzle engine now has **two additional genuine output paths**:

- \`dragon_native_windows.py\`: opt-in, fixed-command MinGW-w64
  cross-compilation creates an actual Windows x86_64 PE32+ \`.exe\`.
  The offline verifier checks the native PE signature, machine type,
  optional header, entry point, bounded section table, SHA digests,
  identical original source and all solver-proven source-level stages.
  A Windows EXE built on Linux is **not executed** on Windows, and
  \`windows_runtime_verified\` and \`host_execution_verified\` are both
  permanently false in this receipt.
- \`dragon_native_desktop.py build --target steam_deck\` uses the real
  native Linux C99 game pipeline and performs actual ELF execution with
  stage replay and independent physics on the authorized Linux host.
  The target is Steam Deck-compatible source intent; the Linux host
  run is **not SteamOS hardware or input-device certification**.

\`\`\`sh
# On an authorized Linux build host with MinGW-w64 installed:
python -m skeleton.ai.webcrawler.dragon_native_windows build \
  --title "Original Dragon Windows Puzzle" --stages 4 \
  --seed 1977 --attest-original-rights --authorize-cross-compile \
  --out ./original-windows-build

# Actual Linux ELF, target-specific source and native gameplay replay:
python -m skeleton.ai.webcrawler.dragon_native_desktop build \
  --target steam_deck --title "Original Dragon Steam Quest" \
  --stages 4 --seed 1977 --attest-original-rights \
  --authorize-local-build --out ./original-steam-deck-build
\`\`\`

The GitHub native workflow has a separate job that installs
\`gcc-mingw-w64-x86-64\`, compiles original Win64 source,
inspects the actual PE bytes and packages the release. These
are independent target-admission and structural verification claims:
Windows runtime playtesting remains a distinct incomplete task.

### Saving and importing original game editor projects

The mobile/web grid editor now supports user-controlled export of its
exactly solver-validated board pack as bounded versioned JSON with
canonical campaign digest. On web it downloads a content-addressed
\`.json\` file; on native mobile it saves and offers OS sharing.
Import goes through the OS document picker, enforces the 8 KiB limit
and strict 12×10 grid shape and **immediately drops earlier validation**.
Imported maps must be revalidated by the authenticated backend before
source generation can resume. Raw arbitrary files and script execution
are not accepted.

### Native macOS original-game executable and real host playtest

\`dragon_native_macos.py\` provides an explicitly authorized, macOS-host-only
game builder. It uses the existing canonical original C99 Sokoban generator
for \`pc_macos\`, invokes the installed Apple C compiler, checks that the
output is a valid bounded 64-bit Mach-O native executable for the actual
host CPU (x86_64 or arm64), then **runs that executable**.

The local builder exercises its \`--selftest\`, \`--hint-selftest\`,
\`--challenge-selftest\`, and three independent movement/undo/reset
simulation traces for *each* level. It compares native executable states
to the independent Python puzzle physics before publication. The ZIP
includes the original-source release, actual Mach-O executable and
scoped runtime evidence.

\`\`\`sh
# Run on an authorized macOS host with Xcode command-line C tools installed:
python -m skeleton.ai.webcrawler.dragon_native_macos build \
  --title "Original Dragon Mac Adventure" --stages 4 \
  --seed 1977 --difficulty 6 --attest-original-rights \
  --authorize-local-build --out ./original-macos-game
\`\`\`

\`verify\` checks the Mach-O header/architecture, load command bounds and
entry point, original source and grid proofs and the builder's reported
runtime results **without executing a downloaded executable**. The
macOS-15 CI job must actually build and execute the generated game;
the response must not claim Apple Silicon or physical-device testing unless
the selected runner genuinely provides that hardware. Mac App Store
signing, notarization, OS compatibility across versions, and controller
support remain separate operational releases and are not asserted here.

### Real native game editor, playtest, saves and rewards

Dragon's original puzzle creator now supports a complete interactive
authoring loop:

1. Create or import one to eight original 12×10 game boards and paint
   walls, paths, crate goals and the player in Expo.
2. **Play-test the actual grid data** with directional controls, pushes,
   undo and reset using bounded local Sokoban physics; this browser/mobile
   preview never substitutes for native C99 runtime proof.
3. Validate each level's existence, unique grid identity and solver-optimal
   path on the backend, then explicitly approve it for source export.
4. Build the same original level data as a real C99 game for Linux, macOS
   or a Windows x64 build; use local binary execution tests where supported.

The C99 game includes a bounded live-current-position shortest-path hint
solver, on-screen optimality-derived star grading, and a small local
\`dragon-save-v1.dat\` save/resume slot (interactive K/L, native SDL F5/F9
or supported gamepad controls). A save is bound to the exact generated
campaign geometry and rejects malformed, mismatched or corrupt state.
This is a local user game save, not cloud identity, user tracking or
permission to rewrite Jeeves memory.

A graphical **SDL2 renderer** is now included with every original puzzle
project as a separately compiled optional target (\`make graphics\`).
Its actual C99 game engine is included directly, not rewritten as a
browser imitation. The 640×480 native game window uses original 2bpp
inspired pixel art and real creator-selected protagonists and biomes.
Its gameplay includes keyboard/controller input, goals, crates, stage
progression, native stars, efficiency HUD and victory state. The terminal
game still compiles without SDL2.

### Source-grounded gameplay screenshots and storyboards

For an original Linux game, a separate operator-approved local mode
compiles the SDL2 source, executes the gameplay with a software renderer
and captures an actual BMP image of each level at start, midpoint and
completion. The source, SDL ELF, screen frames and hashes are packaged
and independently audited. The screenshots are **only generated original
game frames**—there is no general screen recorder, website recorder
or capturing the user's machine.

\`\`\`sh
python -m skeleton.ai.webcrawler.dragon_native_capture_operator capture \
  --title "Original Dragon Gameplay" --seed 1977 --stages 3 \
  --attest-original-rights --authorize-local-capture \
  --out ./original-game-capture
\`\`\`

To turn those real original frames into a reviewable portable PNG contact
sheet (three columns start/middle/solved; one row per level), use:

\`\`\`sh
python -m skeleton.ai.webcrawler.dragon_native_media_storyboard \
  --capture ./original-game-capture/dragon-original-game-frames-<digest>.zip \
  --out ./original-game-storyboard --authorize-storyboard
\`\`\`

The storyboard is generated from verified BMP bytes using a bounded
standard-library PNG encoder and published as both an actual \`.png\`
and an immutable ZIP containing the exact original capture and receipt.
Verification reconstructs the storyboard pixels from those source frames,
so a repainted or substituted image fails offline audit.

These capabilities provide real, source-grounded visual review and
playability evidence where GitHub's native build runners execute.
They do not assert emulator compatibility, pixel-exact physical console
capture, verified controller hardware, OS signing, independent publisher
authentication, or subjective game quality. The cross-platform build
gates must still pass on the exact PR head before production signoff.

### Release verification and index integrity

A release index is **not trusted merely because its archive hashes match**.
The independent verifier now recomputes aggregate evidence level,
source/binary state, style, per-platform gameplay mode, claimed fidelity,
source budget, release inventory and the legal-claim limitation from verified
nested release receipts. Altered top-level labels are rejected even when
individual source ZIP bytes remain unchanged.

Self-contained hashes provide corruption and consistency detection, **not**
publisher authentication or tamper-proof origin against an actor who can
replace every archive and index. Independently keyed release signatures and
trusted builder custody remain future requirements for stronger origin proof.

## What the outputs mean

- `source_generated`: original platform source files were emitted, budget
  audited, hashed, archived and individually verified. No compiled binary
  or runnable ROM is claimed.
- `rom_structural_verified`: a local established compiler path emitted
  a structurally valid ROM and its digest was rebound to the archive.
  It is *not* evidence of emulator playability, original-hardware execution,
  user experience, performance or store acceptance.
- `matching_declared_modes_not_verified_equivalent`: the requested target
  releases have the same *declared runtime mode*. This is not an assertion
  of feature-equivalence, identical feel or asset parity.
- `different_implemented_modes_not_an_equivalent_port`: target source
  producers implement distinct game modes. These are related original
  practice releases, **not** a bit-for-bit or gameplay-equivalent port.
- `toolchain_missing`: an optional ROM compilation attempt was requested
  but the toolchain was missing. Source-only delivery remains honest unless
  `--require-compiled` forbids it.
- `blocked`: unavailable hardware emitter, restricted SDK, unsupported
  style or mandatory compiler requirement. The whole batch halts with no
  production files written.

The rights attestation is an operator declaration only. Original platform
homebrew may still require legal review of branding, distribution rights,
third-party assets, SDK terms and patents by jurisdiction; there is no DRM,
firmware, BIOS, game copy, commercial ROM, stolen key or jailbreak workflow.

## Files and source of truth

- `dragon_native_production.py`: pure preflight, archive packaging,
  local bounded batch publication and independent verification.
- `dragon_native_cli.py`: existing creator entrypoint, backwards-compatible
  with its original single target commands.
- `dragon_native_projects.py`: canonical hardware source emitters;
  not duplicated or replaced.
- `dragon_native_targets.py`: authoritative target capability names and
  available gameplay styles.
- `dragon_hardware_budget.py`: existing conservative source budget auditor.
- `dragon_native_compile.py`: existing strictly allowlisted ROM compiler.
- `tests/test_ai_dragon_native_production.py`: real generator regression,
  negative cases, archive attestation, CLI integration and repeat verification.

## Operator safety / recovery

Source and archive objects are generated and checked in memory first.
Publication creates immutable files via fsynced staging and a no-overwrite
filesystem hard link, then publishes the index LAST. A failed or interrupted
run can be retried: matching byte-identical destinations are accepted;
conflicting destinations fail closed. Interrupted temporary staging files
can be removed manually when no job is active. Never automatically delete
unrecognized user files during recovery.

Do not invoke optional native compilation on a privileged machine or inside
a public HTTP handler. A local C/ROM compiler is not an untrusted-source
sandbox: CI should use a restricted build runner, fixed toolchains, and
separate trust zones. This release lane neither escalates builder authority
nor extends the supervised research/knowledge promotion surface.

## Required validations for promotion

    python -m pytest -q tests/test_ai_dragon_native_production.py
    python -m pytest -q tests/test_ai_webcrawler_dragon_native_projects.py
    python -m pytest -q tests/test_ai_webcrawler_dragon_native_compile.py
    python scripts/check_architecture_map.py
    python scripts/check_ai_app_construction.py
    python scripts/check_capability_interfaces.py
    python scripts/check_provider_bootstrap.py
    python scripts/check_ai_file_tree.py
    python scripts/check_enterprise_ai_superiority.py --json
    python scripts/check_enterprise_ai_implementation_notes.py --json

Additionally, exercise the application CI, exact-head App Assembly and
cross-platform gates. **A test file in the repository is not a passing test
result.** Do not sign complete/merged/released status until actual runs
succeed against the final head.

## Deferred production-grade enhancements

Real emulator automation with frame traces and input replay; original
hardware smoke matrices; actual localized console toolchain builds beyond
GB/CGB/NES; editor-level game-design round-tripping; developer asset
preview and diff; gameplay fidelity evaluation across ports; provenance
signatures using independent trusted keys; full installer/artifact uploads;
localized accessibility and control-scheme QA; copyright and SDK-terms
counsel review; and actual user-facing Studio status integration beyond the
existing native CLI. These are **not** asserted by this delivery.
