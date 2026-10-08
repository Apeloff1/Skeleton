# Dragon Native Game Forge — true hardware eras, not browser skins

This extends the existing policy-bound crawler's Dragon Academy. The old
HTML prototype is maintained for backward compatibility; **new learning
practice defaults to original native source projects**.

## Hardware coverage

The \`dragon_native_targets.TARGETS\` table currently covers **47**
hardware/operating-system targets (1977 through modern desktops), grouped
by lineage, CPU/graphics/sound/input constraints, expected binary format,
toolchain and adapter readiness. There are 30 planned game-style objectives,
but **not all hardware × style combinations have unique gameplay yet**.
Styles without specific native mechanics remain a design direction; do not
mark them complete merely because the manifest names a genre.

Native source emitters in this delivery (16 IDs):

| Target | Project output | Toolchain | Status |
|---|---|---|---|
| Sega Master System | Z80, VDP sprites, native CRAM and controller input | SDCC/devkitSMS | SDK source emitted, not compiled |
| Sega Game Gear | Z80, 160×144 VDP, handheld palette and controls | SDCC/devkitSMS TARGET_GG | SDK source emitted, not compiled |
| Super Nintendo (SNES) | 65816, Mode 1 tiled background, native joypad, LoROM | PVSnesLib | SDK source emitted, not compiled |
| Commodore 64 | 6510 C source + VIC-II/CIA/SID native PRG | cc65/cl65 | Source emitted, compiler smoke optional |
| Nintendo Game Boy Color | CGB-only RGBDS ROM, true OBJ palette RAM | RGBDS | Source emitted; optional GBC ROM compilation |
| Original Nintendo Game Boy | SM83 assembly → \`.gb\` | RGBDS | Source emitted, ROM validation optional |
| Nintendo NES | 6502 assembly + NROM linker → \`.nes\` | cc65 ca65/ld65 | Source emitted, ROM validation optional |
| Sega Genesis / Mega Drive | SGDK C source + Makefile → \`.bin\` | SGDK | Source emitted, SDK build unverified |
| Game Boy Advance | ARM C + MODE 3 framebuffer → \`.gba\` | devkitARM/libgba | Source emitted, SDK build unverified |
| Original PlayStation | PSn00bSDK C + CMake → \`.exe\` | PSn00bSDK | Source emitted, SDK build unverified |
| Original Xbox | nxdk + SDL2 C → \`.xbe\` | nxdk | Source emitted, SDK build unverified |
| DOS VGA PC | DJGPP C + direct VGA framebuffer → \`.exe\` | DJGPP | Source emitted, compiler unverified |
| Linux PC | native C + SDL2/CMake → ELF | SDL2/CMake | Source emitted, compiler unverified |
| Windows PC | native C + SDL2/CMake → \`.exe\` | SDL2/CMake | Source emitted, compiler unverified |
| macOS PC | native C + SDL2/CMake → Mach-O/\`.app\` | SDL2/CMake | Source emitted, compiler unverified |
| Steam Deck | native SDL2/Linux C | SDL2/CMake | Source emitted, compiler unverified |

The original Game Boy and NES emitters include actual native CPU assembly,
ROM header/linker declarations, sprite graphics and controller input.
DOS writes to VGA memory using DPMI; SGDK uses the Genesis pad and VDP;
GBA draws to mode 3 VRAM with keypad input; PS1 uses PlayStation graphics
and pad interfaces; Xbox nxdk adds gamecontroller input to SDL2 visuals.

The 47-target catalog also includes Atari VCS, Intellivision, ColecoVision,
ZX Spectrum, Apple II, Atari Lynx,
TurboGrafx-16, Neo Geo, Amiga, Atari ST, DOS 8086, Windows 95/XP,
Saturn, Nintendo 64, Dreamcast, GameCube, PS2, Nintendo DS, PSP, Wii, PS3,
Xbox 360, Nintendo 3DS, Wii U, PS Vita, PS4, Xbox One, Nintendo Switch,
PS5 and Xbox Series. **Their platform-specific emitters are not complete**
and they must not be counted as having working ROM build support.

Modern Xbox One/Series development requires licensed GDKX rather than the
unrestricted public Windows GDK. Current PlayStation and Nintendo retail
distribution may also require authorized SDK/developer access and compliance
with hardware distribution rules. No commercial ROMs, BIOS images, keys,
device security bypasses or proprietary SDKs are bundled.

## Make an original Game Boy cartridge project locally

Install the open-source RGBDS tools first. From the repository root:

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --target game_boy --out /tmp/dragon-gb

This creates the complete \`src/main.asm\`, \`Makefile\`,
\`README.md\` and \`dragon-native-manifest.json\`.

Then run:

    cd /tmp/dragon-gb && make

The RGBDS pipeline runs \`rgbasm\`, \`rgblink\` and \`rgbfix\`, creating
\`build/dragon.gb\` when all steps succeed.

Or explicitly compile and structurally validate with:

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --target game_boy --out /tmp/dragon-gb-build --compile

The \`--compile\` path only supports GB/NES and only when the required
executables are installed locally. It checks byte-level ROM format/header
consistency, digest and toolchain return codes. **A compiled ROM does not
prove it ran correctly in an emulator or on hardware.** Do an independent
emulator playtest before declaring gameplay validated.

For NES, replace the target with \`nes\`, install ca65/ld65, and expect
\`build/dragon.nes\`. For DOS, use \`dos_vga\` and a DJGPP cross-compiler;
for desktop PC, select \`pc_linux\`, \`pc_windows\`, \`pc_macos\` or
\`steam_deck\`, install the native compiler + SDL2 and run CMake.

For other supported open homebrew SDK source emitters use \`genesis\`,
\`game_boy_advance\`, \`ps1\` or \`xbox_original\`. Their build scripts
intentionally require the user-installed SDK. **They are not validated**
on a real machine until dedicated cross-compiler CI and emulator testing
are added.

## Crawler practice workflow

- \`DragonPracticeLab.offer(ApprovedLesson(...))\`: the canonical crawler
  uses its already-validated knowledge-promotion and human approval receipts.
- \`DragonNativePracticeLab.generate(... target_id, style, consent=True)\`:
  produces deterministic platform source using approved lesson mechanics,
  with owner-scoped SQLite record, digest, one source project per
  claim × platform × style and daily resource ceilings shared with legacy
  HTML practice.
- \`DragonNativePracticeLab.archive(...)\`: exports a deterministic,
  integrity-checked ZIP of source and scripts. **It does not claim a
  compiled file is inside.**
- \`DragonPracticeCycles.enable(generation_mode="native",native_target=...)\`:
  finite, opt-in recurring learning exercises. New backend subscriptions
  select native source emission by default. Missed ticks do not catch up
  automatically or extend the user's explicit authorization.
- \`/api/dragon-academy/native/targets\` lists all families and readiness;
  \`/api/dragon-academy/native/generate\` creates projects from approved
  lessons; \`/api/dragon-academy/native/{attempt_id}/archive\` sends the
  authenticated owner's source ZIP only. The frontend filters the
  available emitters and makes ZIPs downloadable on web and mobile.

**XP policy:** Original source generation is practice, not demonstrated
competence. The existing progression system grants XP for independently
approved knowledge and evidence-backed reviewed gameplay, never just for
labelling a file \`.gb\`, \`.exe\` or \`.xbe\`.

## Required next engineering milestones

1. Native cross-build CI for each installed homebrew SDK (GB/NES first);
   link exact-head tested output digests to practice attempt records.
2. Emulator integration harnesses, CPU/video/input replay, screenshots,
   deterministic test traces and human playtest evidence.
3. Separate per-target engine pipelines (sprites, tilemaps, sound,
   save states, controllers, memory budgets, DMA timing and asset packing).
4. Native emitters for SNES, N64, GameCube, DS, 3DS, Switch, PS2/PSP,
   Wii/Wii U, original Xbox GPU and platform PC builds.
5. Licensed console SDK adapters only for authorized accounts, with
   signed provenance and secrets isolated outside the generated project.
6. Learn mechanics from real game research, not proprietary assets;
   diversify actual gameplay before claiming all 30 styles are supported.

Tests:
    python -m pytest \
      tests/test_ai_webcrawler_dragon_native_projects.py \
      tests/test_ai_webcrawler_dragon_native_compile.py \
      backend/tests/test_dragon_academy_routes.py -q

Frontend:
    cd frontend && yarn test:dragon-companion && yarn typecheck

Build gates must actually pass; skip/missing compilers are not proof.


## Second-generation native game engine: real mechanics and eight-bit pixels

Original SDL2/C99 campaign engine has six distinct movement/gameplay kernels:
score attack, gravity platformer, top-down explorer, connected-room dungeon,
grid movement tactics, and inertia-based racer. Seventeen intended genres map
to those six modes. They are NOT seventeen independently complete games.

Each PC campaign creates four deterministic 32x20 tilemap stages with a
verified route from player spawn to exit, hazards, enemies, pickups, portal,
HP/energy, score, scene transitions, original sprite animations and
synthesized arcade sound. Keyboard and gamepad control are supported.
Cross-compiled platform builds need separate verification.

Eight original sprite tiles now pass through genuine SM83 interleaved and NES
CHR planar 2bpp encoders. The Game Boy dragon has timed blinking animation.

Native practice is bounded to eight seeded challenge variants per approved
claim + platform + style (rather than one exercise). All variants have
different deterministic content; generation never grants extra XP, and
owner/session consent and the total daily practice budget still apply.

The new CI job installs SDL2 + CMake and compiles/runs all six genres in a
headless native SDL environment for 360 simulated ticks each. The cartridge
CI job installs RGBDS and cc65 to compile GB, NES and Commodore 64 programs.
A native smoke test is NOT an independent user acceptance playtest.

Example:
    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --target pc_linux --style roguelike --out /tmp/dragon-rogue
    cmake -S /tmp/dragon-rogue -B /tmp/dragon-rogue/build
    cmake --build /tmp/dragon-rogue/build
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
      /tmp/dragon-rogue/build/dragon_game --smoke

Remaining: 31 catalog hardware profiles do not have dedicated native
emitters; full genre depth, emulator traces, original 3D engines, save systems,
and real-device performance testing are not yet complete.


## Adversarial static campaign-selection cohort

For each native PC game generation, the forge does not settle for the first
random dungeon. It generates eight distinct seeds, reconstructs the tile
graph, computes shortest routes and enemy-exposure-weighted routes, measures
collectible access, dead ends, path detours and explorable coverage, and
chooses the best admissible candidate. Source ZIPs include a machine-readable
dragon-generator-evaluation.json: all candidates, selected static metrics,
selection digest and proof boundaries. A game with disconnected objectives is
rejected rather than granted progress. The builder is not claiming to have
played, tested on actual hardware, trained a model or earned any XP.


## Third-generation cartridge and desktop runtime pass — native, not a skin

### True Color Game Boy cartridge (13th source target)

The Game Boy Color emitter is not a renamed DMG ROM. It adds a native CGB
OBJ palette initialization at FF6A/FF6B (auto-increment in palette RAM),
several original BGR555 palettes, RGBDS CGB-only cartridge header and a
.gbc output artifact. RGBDS rgbfix -C is required. Both header flag and
checksum must be structurally verified by the local native build gate.

For a real local CGB cartridge, install RGBDS:

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --target game_boy_color --out /tmp/dragon-cgb --compile

The binary output, if compilation succeeds, is
/tmp/dragon-cgb/build/dragon.gbc. This is HOME BREW, not a Nintendo ROM
download and not a PlayStation or modern Xbox game. A structural header
check does not show that an emulator has rendered the palette correctly.

### Standalone original scrolling Game Boy platform game

This is a second native Game Boy gameplay engine, separate from the earlier
single-screen score chase. The generated SM83 assembly sets the PPU tile
data at $8000, BG tilemap at $9800, 32-column level collision geometry,
world-space X coordinates, camera SCX register updates, a moving player OAM
sprite, A-button jump impulse, bounded signed falling speed, ledge and
ground landing, scrolling world gem and a blinking hatchling frame.

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --target game_boy --style side_scrolling_platformer \
      --out /tmp/dragon-platform --compile

The CI gate attempts an actual RGBDS ROM build and validates the .gb header.
This is native hardware architecture but it has not yet been demonstrated
on a Game Boy emulator or cartridge. Sprite handling and physics still
need extended player tests, audio, reset options and performance review.

### Native desktop campaign persistence

Each SDL2 campaign now compiles a two-slot checkpoint service. Saves are
36-byte versioned binary records in SDL's application preference directory,
with campaign-signature binding, explicit little-endian fields, per-record
CRC-32, size checks and bounded stage, health, score and monotonically
increasing serial. Two alternating files mean a failed save cannot destroy
both copies at once. Only stage boundaries are autosaved.

The generated native game resumes a valid same-campaign checkpoint on a
normal launch. Pressing R starts a new campaign; a new game checkpoint is
saved at the start of the next stage. No cloud access or server identity
is needed; changing the campaign invalidates stale saves deliberately.
Developer-level native save verification:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
      build/dragon_game --checkpoint-test

### Deterministic native gamepad replay

The desktop game can record the input buttons for exactly up to 7,200
fixed 60-Hz simulation frames and play them again. The versioned binary
DRPL format includes the exact campaign identity, a strict frame limit,
CRC-32 of every controller input, and the expected integer gameplay
state digest. Playback resets game PRNG and world, replays the actual
native physics ticks, and refuses mismatches. No screen/video/microphone
is recorded; the player must opt in to saving a local trace.

    build/dragon_game --record-replay /tmp/practice.drpl
    build/dragon_game --play-replay /tmp/practice.drpl

For CI, a deterministic native 360-tick replay smoke creates a bounded
original input stream, reloads it and verifies end-state equivalence:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
      build/dragon_game --replay-selftest /tmp/practice.drpl

Damaging its payload must cause replay loading to fail. This provides
REPRODUCIBILITY, not a claim of user acceptance, visual quality, correct
emulator behavior, or verified genre mastery. A source-only practice ZIP
still earns zero XP by itself.

The game archive's save and replay .c/.h files compile as native source
together with main.c; no browser WebView is used for these features.

### Next required high-impact steps

- Emulator-based Game Boy and CGB sprite/video frame assertions.
- Separate NES, GBA, Genesis and C64 genre-specific mechanics rather than
  cloning the one-room collectible design onto every console family.
- SNES and N64 2D/3D hardware surfaces and sound toolchain integration.
- A typed, editable game specification with modular assets, scenes,
  progression objectives, configurable bosses, save contents and game
  configuration that compile down to different console constraints.
- Hardware/CI budget checks for VRAM, RAM, ROM banking, scanline quotas,
  input timing, audio buffer underruns, controller mapping and CPU ticks.
- Original Xbox and Sony PlayStation homebrew compilation on legally
  configured SDK runners, then optional partner SDK targets for modern
  consoles. SDK credentials must stay out of source archives.
- Independently verified gameplay/evidence chains that award learning
  promotion only after traceable review, never for build volume.


## Fourth-generation chapter design — actual native quest gating

The campaign builder now performs an extra deterministic placement pass:
early adventure, dungeon and tactics chapters contain a treasure chest;
subsequent chapters add a reachable key and locked door; advanced chapters
add guardians with multiple hitpoints and friendly caretaker encounters.
Each quest placement includes typed coordinates and a SHA-256 evidence digest.

The static compiler checks that a key can be reached from the starting
position without crossing its own locked door. This protects the generated
campaign from a specific class of progression softlocks. It is **not** a
proof that enemy AI can be beaten, that every attack is balanced or that
real player movement will reach the portal under all collisions.

The native SDL2 C engine recognizes keys, doors, chests, NPCs and bosses;
doors block movement until a key is acquired, pickup is recorded, and a
portal does not advance the chapter if a required key was missed or
a guardian remains alive. Guardians have extra HP, pursuit behaviour,
feedback pulses and reward. Chests heal and award score, and friendly
encounters restore energy. All progress is internal to the compiled game,
not crawler mastery XP.

## More actual native console-family source backends

The Sega Master System and Sega Game Gear use documented devkitSMS and SDCC
toolchains with original 8x8 graphics packed into Z80 VDP 4bpp tiles.
The code updates real VRAM and CRAM, reads pad state and synchronizes sprite
SAT writes with vblank. Game Gear uses TARGET_GG and the handheld's 12-bit
palette. The generated Makefiles require an independently installed
devkitSMS, SDCC and makesms; there are no precompiled SDK binaries.

The Super Nintendo source uses native PVSnesLib/65816 with BG mode 1,
VRAM text tile map, built-in SDK font, auto-read joypad, stage transitions,
enemy hazard and HP/game-over loop. Its LoROM Makefile uses PVSnesLib
snes_rules, not a PC CMake target.

These three are source emitters only. Unlike RGBDS and cc65, an actual
SDK build and console emulator run are not yet in CI. Do not present them
as certified playable ROMs or assume toolkit compatibility without proof.

## Gameplay constraints learned this pass

A static cartridge renderer is insufficient if the game cannot be solved.
The original Game Boy scrolling platformer jump arc was too shallow, and
its first design risked leaving the character suspended when walking
off ledges. The new source gives the player a signed -10 jump impulse,
re-evaluates standing support, widens narrow landing windows and alternates
gem objectives between platform heights reached by the player. The RGBDS
CI job will attempt to assemble this corrected real cartridge program.


## Original score composition and authentic handheld APU sound

An era-aware music engine now builds deterministic melodic and harmonic step
sequences for each native PC gameplay kernel. A bounded 64-step tune uses a
genre-appropriate tempo, scale, repeatable phrase structure and rests; output
is human-readable frequency data, not MP3, copyright-mimicking audio, or an
LLM hallucination of a soundtrack.

Each native SDL2 project includes dragon-original-music.json containing the
exact composition, its SHA256 fingerprint, genre, tempo and phrase sequence,
plus include/dragon_chip_score.h with real frequency arrays. The native C
game's fixed-step update drives the SDL audio device with music pitches and
short square-wave harmonies. The score differs between racer, platformer,
dungeon, tactical and adventure styles. Music is original and cheap enough
for prototypes; richer instrument voices, polyrhythm, mixing, frequency
precision and platform audio ceilings remain to be implemented and profiled.

Original Game Boy DMG, CGB and scrolling platformer programs also include
native CPU register code controlling the actual Game Boy APU: NR52 ($FF26)
power, NR50 ($FF24) master level, NR51 ($FF25) routing, NR11 and NR12
duty/envelope, and NR13/NR14 frequency trigger. A single-screen reward is
latched to prevent repeated chimes every game loop, whereas a platformer
collectible produces one chime and moves its goal. This is genuine
hardware sound generation, not an HTML audio element.

These enhancements must also pass RGBDS ROM compilation and emulator sound
checks before claiming audible output on physical handhelds.


## Fifth-generation native game architecture: typed design, 3D, graphics, budgets

### Strict offline user-editable game specifications

The game design compiler accepts canonical JSON with a title, target,
genre, palette, stages (1-8), selection candidates (1-24), uint32 generation
seed, difficulty annotation (1-10), named original hero/theme, and bounded
notes. It rejects missing/extra keys, duplicate JSON keys, invalid field
types and command-shaped/path-injection text. The design changes the actual
generated stage count, palette, candidate budget, and deterministic seed.
The designer currently records the difficulty, hero and theme; it does not
yet implement unique mechanics for those annotations. No approval, XP or
owner authority is derived from a design file.

To create the design data, run Python and import starter_design from
skeleton.ai.webcrawler.dragon_game_design, then save its dictionary as
/tmp/dragon-spec.json. Edit stages, candidates, seed, genre, palette and
target within the validated supported options. Run:

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --spec /tmp/dragon-spec.json --out /tmp/dragon-fps

The source project includes a canonical designer fingerprint in
dragon-game-design.json plus the generated campaign and candidate reports.

### Dedicated native software-raycasting engine

For first_person_shooter and immersive_sim, the PC targets now use
dragon_native_raycaster.py rather than the existing 2D top-down engine.
It emits real SDL2/C99 with first-person DDA wall stepping, camera rotation,
perpendicular wall depth, perspective stripe rendering, collision,
depth-clipped enemy billboards, combat, key-door interaction, health, and
four or more native chapters. The same renderer currently underlies both
genre labels; neither genre is a finished commercial FPS or immersive sim.
This implements early PC-era 2.5D software perspective, NOT a 3D GPU,
PlayStation or modern Xbox engine. The native CI includes a 480-tick
headless diagnostic exercising the actual raycaster executable.

### Original 4bpp sprite hardware encoders

The atlas compiler produces and checks four distinct native memory layouts:
SNES Mode 1 interleaved 4bpp planes, GBA packed low-nibble-first 4bpp,
Genesis packed high-nibble-first 4bpp, and Sega SMS/Game Gear per-row 4-plane
VDP graphics. Decoding must reproduce every authored tile without loss.
The GBA Mode 3 C framebuffer draws the generated original hatchling from
its packed 4bpp atlas and BGR555 palette rather than a generic solid block.

The SNES and Genesis source archives carry their era-correct encoded
graphics with a fingerprint, but their present native game loops do not yet
consume/upload them. They must not be claimed as working on-screen sprite
renderers. The SMS and Game Gear have VDP sprite loading separately.

### Conservative hardware resource audits

Every emitted native source bundle now carries
dragon-hardware-budget.json. The auditor checks and reports source bytes,
declared graphics atlas bytes, target-specific sprite/tile budgets, video
storage classes, RAM and ROM-bank development constraints across 16
supported native emitter targets, with explicit warnings and SHA256 evidence.
These are SOURCE-level constraints and NOT native linker allocations,
cycle-accurate VRAM/OAM scans, or actual hardware certifications.

Native compiler outputs, emulator replay, hardware profile instrumentation,
visual gameplay quality and accessibility remain independent gates.


## Sixth-generation AI game-building practice: explicit objective planning

Source-only generation no longer stops at making a procedural dungeon.
The planner now runs bounded state-space navigation over each original
chapter. It tracks current position, whether a collectible key was picked
up, whether a door was opened, and whether abstract boss obligations are
satisfied. It emits a reproducible action sequence: step east/west/north/
south, pick up a key, unlock a door, collect arena crystals, abstractly
resolve a guardian encounter, and reach the portal.

For score-attack arenas, the planner explicitly visits every collectible
before the final exit. For adventure, dungeon and tactical games, it
checks a dynamic key-door progression path rather than just treating all
map cells as free space. Routes are threat-weighted to avoid close enemy
cells when alternatives exist. Search is capped at 16,000 visited
states per route and 4,000 actions per stage, and it fails on unsolved
objectives rather than crediting false AI progress.

Every generated desktop source archive includes dragon-playtest-plan.json
with a chapter-by-chapter route and reproducible digest, including explicit
disclaimers: boss victory is assumed in this abstract path planner; native
controller movement, real physics, moving combat AI and actual player
success are NOT verified by the plan. No game mastery XP is awarded.

## Actual use of editable difficulty, hero and world theme

The typed design file no longer records all customization as inert notes.

- Difficulty 1..10 changes generated native enemy count and campaign
  difficulty, plus native 2D and first-person enemy HP and movement speed.
  It is included in the campaign identity and candidate search.
- The native 2D renderer now draws six distinguishable original protagonist
  silhouettes: hatchling, knight, explorer, pilot, astronaut and robot.
  These are simple procedural pixel shapes, not completed character rigs.
- All seven original world themes alter the native tile highlight palette
  and 3D raycast wall colour from compile-time generated constants.

The source remains bounded, reproducible and platform-specific. Runtime
verification requires native compiler and player tests. Current source
files are NOT an advanced AI game mastery certificate.


## Seventh-generation cryptographic native build evidence custody

A source file, a source code ZIP and a structurally accepted compiled ROM
are three separate states. The new DragonBuildEvidence ledger exists
beside the owner-scoped native practice lab, sharing its authoritative
SQLite database and canonical lesson-to-attempt source digest.

It requires an isolated trusted compiler worker, not a browser request.
The operator provides a 256-bit+ private signing key in worker memory.
When that worker submits *actual native binary bytes*, the ledger checks:

1. The owner-scoped attempt exists and its stored source files still match
   the immutable source fingerprint.
2. The binary is bounded and its platform/compiled format is recognized
   (currently GB, GBC and NES).
3. The cartridge header/size/checksum is structurally consistent, and the
   compiler identity matches its declared native target.
4. A new receipt is content-addressed by the binary SHA256 and source digest,
   signed with HMAC-SHA256, linked to the previous digest, indexed in a
   per-owner append-only chain and committed transactionally.
5. Reimporting identical binary bytes for the same attempt returns the
   earlier receipt without duplicating claimed progress.

The verifier recomputes the chain and HMAC when reading; tampered receipts
fail closed. Signature rotation and direct database manipulation by an
operator need separate key lifecycle controls. The current evidence
claim is ONLY that *ROM bytes and header are structurally checked by the
configured trusted worker*, not that the source compiled on an actual
vendor SDK, an emulator has executed it, hardware passed certification,
or a player accepted the game.

The product route GET /api/dragon-academy/native/evidence requires an
authenticated owner and the operator's
SKL_DRAGON_BUILD_SIGNING_KEY_HEX (minimum 64 hex digits).
It only reads up to the latest 50 verified receipts, after validating the
full owner chain. There is NO public build-signing POST endpoint, NO
untrusted direct ROM upload to the signer, and NO automatic gameplay XP.

Future dedicated workers must link exact-head GitHub CI build jobs,
toolchain digests and independent emulated input/video/audio traces before
claims can advance beyond structural binary validity.


## Eighth-generation distinct native genres: turn-based RPG and rhythm game

A genre-name catalogue does not justify pretending the same arcade collector
is a tactical game, RPG, dance simulator and 3D FPS. These two new native
C99/SDL2 engines are separate from the six initial 2D gameplay kernels
and the previously implemented first-person DDA dungeon engine.

### Original turn-based RPG engine

Select target pc_linux, pc_windows, pc_macos or steam_deck and style
turn_based_rpg. The generated source uses an actual EXPLORE/BATTLE/DEFEAT/
VICTORY state machine rather than continuous real-time collision damage.

The player character has persistent in-memory RPG stats: HP/max HP,
MP/max MP, level, XP, attack, defense, money, keys, crystal inventory,
potions and ether. Battles have separately defined actionable turns:

- Sword strike: compare hero attack with the enemy level and bounded RNG.
- Magic: spend three MP to bypass armor for greater damage.
- Guard: reduce the next enemy turn's retaliation.
- Potion/ether: consume actual limited inventory and restore resources.
- Failed resource action: cannot silently spend a turn.
- Victory: XP, level-up rules, richer statistics and money/loot.
- Guardian defeat: unlock chapter progression and bonus supplies.

Exploration includes native tile maps, discrete grid movement, enemy
encounter detection, world keys/locked doors, treasure and healer NPC
interactions, stage transitions and game-over/victory rendering. SDL
keyboard and gamepad inputs have distinct mappings. The --smoke native
program synthesizes a real battle and requires the player XP reward path
to be reachable. This is not yet a commercial turn RPG: combat balancing,
proper dialogue, animations, inventory menus, tactics, save games and
user playtests require more work.

### Original native rhythm game

Choose style rhythm_game on the same PC target family. This bypasses
the dungeon layout optimizer because the layout would NOT be used by
a music game. It instead compiles actual original song charts, generated
from the chiptune composer, as bounded static C note tables. Each song
has 64 timed notes across four input lanes; each note has a frequency,
lane and target 60Hz simulation frame.

The runtime judges real keyboard/gamepad input against grade windows:
perfect, good, early, incorrect lane, or automatic missed notes. It tracks
combo/max combo, score, HP, song transitions and failure/victory. Audio
plays a short synthesized pitch on an accepted hit through the native
SDL device. The game design difficulty changes actual judgement windows
and note spacing, so a harder source project is not just a metadata label.

The native --smoke path advances through every song frame, inputs every
note at its proper time and verifies the actual hit, miss, combo and
victory state machine. It does not claim the original music is polished
or that a human player enjoyed the game.

The user-editable game design sets the count of native rhythm songs (1-8)
and turn-RPG chapter count (1-8). These engines are compiled from original
source; native CI status must be checked before claiming that actual
binaries built or that physical devices played them.


## Ninth-generation native acquisition: evidence-gated curriculum

The game builder now includes a finite DragonNativeCurriculum that selects
game-building exercises by missing capability and trusted binary evidence.

It starts with Game Boy input/2bpp sprite practice. Only after a trusted
source-bound Game Boy ROM structural receipt exists does it unlock the
Game Boy platformer, NES 6502 exercise and CGB palette training.
NES and CGB receipts unlock broader C64, Master System, Game Gear, GBA,
16-bit VDP, DOS VGA, desktop SDL, first-person, turn RPG and rhythm-game
projects. Later PS1 and original Xbox source exercises remain SDK-dependent
and are NOT automatically counted as working games.

The curriculum refuses to equate a source-generated game with mastered
hardware. It reads the authoritative native attempts from SQLite,
verifies signed ROM evidence only if the operator key is configured, and
prioritizes genuinely new target/genre gaps over repeating similar source
variants. Eight variants per approved lesson/platform/genre are the cap;
the total daily native/HTML budget is shared and the user controls opt-in.

Authenticated API routes:
- GET /api/dragon-academy/native/curriculum: recommended target, unlocked
  tasks, blocked requirements, source attempt history and evidence tier.
- POST /api/dragon-academy/native/curriculum/generate: requires explicit
  approved=true, authoritative owner, reviewed knowledge and the existing
  practice quota. This generates source, NOT a compiler or public XP mint.
- The React Native/Expo Studio companion displays this evidence tier,
  next target and genre, prior attempts and an explicit Generate suggested
  practice game action. Evidence tier is distinct from dragon XP.

The existing finite DragonPracticeCycles controller also supports
curriculum mode. Companion opt-ins set adaptive=true; manual API
subscriptions still default to adaptive=false for compatibility.
A trusted host must invoke pulse() before any scheduled work executes.
Subscription creation does NOT launch unbounded background workers.
Expiration, maximum ticks, revocation and shared daily attempt quotas
remain mandatory.

A structural ROM receipt can unlock later source study. It cannot award
real playability, human enjoyment, AI capability mastery or commercial
SDK certification. True compiled, emulator-tested and reviewed outcomes
require independently traceable tests and human approval.


## Tenth-generation native console expansion: N64, DS, PSP

The source generator now supports 19 distinct native hardware/project targets
out of 47 catalogued platform profiles. The three additions here are
separate native SDK applications; they are NOT compiled binary artifacts.

NINTENDO 64 / libdragon: The VR4300 source runs a genuine 320x240 libdragon
display-surface render cycle (display_init, display_get, display_show)
and hardware joypad poll. An original procedurally drawn hatchling uses the
analogue joystick or D-pad to collect goals, avoid an escalating pursuer,
retain health, and restart on defeat. A libdragon Makefile targets a .z64
ROM. SDK binary compilation and physical N64/emulator frame validation
remain pending.

NINTENDO DS / libnds: The ARM9 source uses BG Mode 5, VRAM bank A and a
16-bit 256x192 bitmap for the primary game display. A lower-screen
console presents the current level, lives and points; touchscreen input
aims a collection pulse against the virtual target location. D-pad
movement, scoring, staged challenge and fail/retry are independent DS
gameplay. The devkitPro/ndstool source build requires separately installed
libnds, ARM9/ARM7 startup and a real SDK verification. No .nds file is
manufactured from C text.

SONY PSP / PSPSDK: A distinct handheld Allegrex console program reads the
PSP controller, analogue nub and directional buttons, synchronizes to
the LCD VBlank, and draws a 57-column original grid game with a crystal,
pursuer, escalating speed, health, and game-over/retry using the PSPSDK
debug-screen. EBOOT.PBP is the toolchain output goal. Proper SDK
compilation and emulator replay remain unverified.

The hardware budget tables include conservative source-level VRAM/RAM and
graphics limits for all three additional targets. Native tests verify the
different rendering/controller APIs, deterministic source output, format
tags and SDK project recipes. They do not claim a compiled, executable,
emulator-tested or licensed commercial game.


## Eleventh-generation actually executable PC puzzle engine with exact solver

The new fixed_screen_puzzle style is implemented as a separate, dependency-
free C99 native Sokoban game for the desktop platform family: Linux,
Windows, macOS and Steam Deck. It DOES NOT invoke SDL, browser code or
a runtime interpreted scripting engine. It produces a regular CMake
project and conventional native Makefile; the host C compiler creates
the resulting binary (including native .exe via an appropriate Windows
compiler). An actual local binary still must be compiled by the user or
CI; source generation alone is not an executable.

The native game implements 12x10 original tile levels, walls, movable
crates, matching goals, character motion, bounded undo history, reset,
a hint for the start state, terminal colour highlighting and progression
only after every crate occupies a goal. It supports keyboard W/A/S/D,
U/R/H/Q/N commands, plus self-test/list diagnostic modes.

Unlike simply inventing a maze, the Python game design compiler solves
EVERY proposed level with finite exact breadth-first state-space search
over both player position and all crate positions before creating the
native project. It rejects any candidate with no solution, improper
crate/goal counts, unrecognized characters, excessive solver states
(120,000 cap), or excessively long solution (400 move cap).
Original hand-designed challenge templates are transformed in deterministic
horizontal/vertical orientations. The editable GameDesign file controls
the level count, generation seed and puzzle difficulty (how quickly the
two-crate templates appear).

The project includes dragon-puzzle-proof.json, containing a bounded shortest
walk, per-level input/output fingerprints and exact source-level search
statistics. Its embedded C puzzle engine then provides --selftest to run
those same move inputs through the real compiled push/collision rules and
confirm the victory state on EACH level. CI includes an actual native CMake
build of the exported game and requires the four-stage self-test to pass.

Run the source forge:

    python -m skeleton.ai.webcrawler.dragon_native_cli \
      --target pc_linux --style fixed_screen_puzzle \
      --out /tmp/dragon-puzzle

Compile and play the actual local game:

    cmake -S /tmp/dragon-puzzle -B /tmp/dragon-puzzle/build
    cmake --build /tmp/dragon-puzzle/build
    /tmp/dragon-puzzle/build/dragon_game --selftest
    /tmp/dragon-puzzle/build/dragon_game

This provides an explicit source -> compiler -> native game -> real move
replay loop, not merely an LLM claim that a puzzle is solvable. The game
remains a deliberately compact native terminal title; sound, animations,
GPU rendering, and human quality reviews require further engineering.
