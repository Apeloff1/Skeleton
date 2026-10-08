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
