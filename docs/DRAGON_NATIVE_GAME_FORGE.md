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

Native source emitters in this delivery (12 IDs):

| Target | Project output | Toolchain | Status |
|---|---|---|---|
| Commodore 64 | 6510 C source + VIC-II/CIA/SID native PRG | cc65/cl65 | Source emitted, compiler smoke optional |
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
ZX Spectrum, Apple II, Master System, Game Gear, Atari Lynx,
TurboGrafx-16, SNES, Neo Geo, Amiga, Atari ST, DOS 8086, Windows 95/XP,
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

Remaining: 35 catalog hardware profiles do not have dedicated native
emitters; full genre depth, emulator traces, original 3D engines, save systems,
and real-device performance testing are not yet complete.
