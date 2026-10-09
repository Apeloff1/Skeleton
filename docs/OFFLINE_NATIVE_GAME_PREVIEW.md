# Native offline game preview and acceptance

The Skeleton offline game-development lane now builds a **real native
Windows desktop executable** named \`SkeletonGame.exe\`. It is a small
playable, model-free game, with source-level tools to generate, compile,
inspect and simulate original 2D levels.

This is not HTML, a browser demo, a Game Boy cartridge, a Nintendo,
PlayStation or Xbox binary, nor a completed general-purpose game
creation environment. It is a verified native playable step toward
future target-specific game exporters.

## What is implemented

The engine-neutral deterministic gameplay layer provides six additional
operations in \`skeleton/ai/runtime/gameplay_capabilities.py\`:

| Operation | Purpose |
| --- | --- |
| \`game.level_generate\` | Build an original, bounded seed-driven map with a guaranteed path |
| \`game.level_compile\` | Check terrain, spawn/goal, walkable reachability and geometry |
| \`game.scene_compile\` | Produce target-independent collision rectangles and player/goal entities |
| \`game.platformer_step\` | Advance a 1x1 player using integer-tick gravity, movement and collision |
| \`game.platformer_replay\` | Replay up to 64 bounded controller frames with SHA-256 trace |
| \`game.tile_line_of_sight\` | Perform deterministic integer grid ray casting against walls |

This raises the model-free operation catalog to **30**. Each function is
bounded, produces a deterministic receipt, and requires no inference,
training examples, network service or proprietary assets.

## Native playable game

On Windows after installing the Skeleton setup, open:

**Start Menu > Skeleton > Skeleton Game Preview**

or launch the installed \`SkeletonGame.exe\` directly.

Alternative entrypoints:

\`\`\`powershell
SkeletonOffline.exe --game-preview
SkeletonOffline.exe --game-preview --game-seed 42
\`\`\`

\`\`\`sh
python -m skeleton app local-ai --game-preview --game-seed 42
\`\`\`

Keyboard controls in the Tk game window:

- **A / D** or left/right arrows: horizontal movement
- **Space / W / up arrow:** jump when grounded
- **R:** restart the level
- **Escape:** exit

The player is a native-drawn sprite and the yellow marker is the goal.
The map contains reproducibly seeded overhead platforms and an
intentional guaranteed ground corridor so the basic player controls
can reach the goal. Collision, gravity and win detection are supplied
by the same \`game.platformer_step\` primitive tested headlessly.

The default preview is 18x12 tiles, with a 28-pixel tile size and
100-ms simulation ticks. It is deliberately small enough for ordinary
consumer-grade PCs. It uses standard-library Tk graphics; no webview,
downloaded images or game-engine service is used.

## Play an original homebrew-only edited project

The native preview is no longer limited to its embedded procedural
demo. It accepts an **explicitly user-selected** portable project JSON
from the cross-era game authoring pipeline:

\`\`\`powershell
SkeletonGame.exe --project .\my-edited-game.json
SkeletonOffline.exe --game-preview --game-project .\my-edited-game.json
SkeletonOffline.exe --game-preview-check --game-project .\my-edited-game.json --json
\`\`\`

The loader refuses symlinks, oversize files, duplicate JSON fields,
forged release flags, altered rights manifests, replaced source asset
hashes, broken edit replay, fake console export claims and unsupported
tile formats. A bounded real-controller solver must find a winning
sequence under the exact movement/jump/gravity rules before the
imported game can be previewed. If it cannot prove playability within
its resource cap, it declines rather than declaring the game valid.

The native renderer adapts to the authored map dimensions (5-32 tiles
per side), and the background scene is built from that map rather
than copied copyrighted game artwork. Entirely original homebrew provenance must be recorded in the project; author declarations remain
**unverified** until a qualified rights review.

Use \`scripts/game/game_project.py --compose <input.json> --output
<new-project.json>\` to make a new private project after applying
bounded authorized tile modifications. This does not implicitly
authorize distribution, console build access or model training.

## Enhanced original-homebrew Windows destination ports

Original games can now be upgraded in Windows using seven original art directions, higher-resolution tile rendering, generated decorations, a camera, accessibility controls and five real hybrid modes. All effects preserve the authenticated source game physics; the port is independently replayed to a winning state. Use the native editor **Windows Port Studio**, or run `scripts/game/port_homebrew.py` and play with `SkeletonGame.exe --project original.json --port-blueprint enhanced.json`. This feature does not import, re-skin or reproduce third-party games. See [Homebrew Destination Adaptation](HOMEBREW_DESTINATION_ADAPTATION.md).

## Play genuine original CHIP-8 machine code in a native window

\`\`\`powershell
# A real native 64x32 CHIP-8 framebuffer, original homebrew game,
# keypad controls with arrows/WASD, R restart, Escape to exit:
SkeletonGame.exe --chip8-demo

# Verify the same ROM's actual generated bytecode and winning controller
# path with no display, using the installed standalone executable:
SkeletonOffline.exe --chip8-demo-check --json

# Write an original playable .ch8 file, not a simulated screen capture:
SkeletonOffline.exe --chip8-demo-output .\original-chip8.ch8
\`\`\`

The native CHIP-8 player runs actual virtual-machine instructions, not
Tk-only approximations of how the ROM should move. The embedded emulator
supports classic CHIP-8 instructions, keypad input, sprites, timers,
registers, RNG and explicit compatibility quirks. Independent original
ROM build/replay and Windows packaging checks are required in CI.
Original hardware compatibility, external-asset publication rights and
actual sound/timing remain unverified and must not be signed as done.

See [CHIP-8 Original ROM Export](CHIP8_HOMEBREW_EXPORT.md) for full
memory bounds, reproducibility, legal boundaries and release checklist.

## Headless actual-play qualification

To prove the frozen runtime can **win** without a display:

\`\`\`powershell
SkeletonOffline.exe --game-preview-check --game-seed 1729 --json
\`\`\`

This instantiates two independent game sessions, simulates the same
controller inputs on each, verifies each intermediate position stays
inside walkable level geometry, verifies both traces match byte-for-byte,
and requires the actor to reach the goal. The JSON receipt contains a
SHA-256 of the replay, seed, frame count and explicit false claims for
model inference, network access, added training rows and desktop
display acceptance.

\`\`\`sh
python -m skeleton app local-ai \
  --game-preview-check --game-seed 1729 --json
\`\`\`

The Windows Installer CI runs this **through the installed
\`SkeletonOffline.exe\` twice**, requiring both processes to produce the
same replay digest, and rejects an invalid negative seed.

This certifies the deterministic native game simulation but **does not**
certify that a visible Tk window actually opened on a user's desktop.
An interactive target-device check remains a separate release
requirement.

## Actual Windows package

The Windows installer builder now emits three distinct executables:

| Executable | Function | Model required? |
| --- | --- | --- |
| \`Skeleton.exe\` | Main setup/application launcher | No for setup |
| \`SkeletonOffline.exe\` | Offline AI console, game tasks, headless acceptance | No for game tasks |
| \`SkeletonGame.exe\` | Dedicated, clickable native graphical 2D game | No |

\`packaging/windows/game_preview_entry.py\` is the game's explicit
PyInstaller \`--onefile --windowed\` entrypoint. The build fails if
the expected \`SkeletonGame.exe\` is missing. Inno Setup installs
all three under the selected application directory and creates a
dedicated Start Menu shortcut.

The installer workflow confirms the game binary exists and is not
a suspiciously tiny placeholder. It also runs the native gameplay
checks through the **installed console**. Do not interpret static
contract checks or queued workflow runs as successful Windows
execution.

## Security and quality boundaries

The game preview accepts a bounded integer seed, not arbitrary Python,
scripts, executable paths, external images or links. The GUI can only
alter local in-memory game state. A separate typed capability graph
can compile a procedural level into an engine-neutral scene; the graph
never grants shell, network, file-write or game-engine plugin authority.

Regression tests address:

- Deterministic procedural generation across different seeds
- A guaranteed 1-tile-wide descent shaft and walkable ground lane
- Collisions and gravity without tunneling through solid tiles
- Reachable, actual gameplay goal and stable post-win terminal state
- Restart restoring the initial actor without changing the world
- Rejecting nonsensical seeds and non-boolean controller inputs
- Keyboard/window drawing using a fake Tk backend in headless CI
- Clean error when Tk is absent or a desktop display cannot open
- Running headless game acceptance without Tk or a language model
- No mutation of the source training-data bank
- Installer packaging of a full native game executable and Start Menu entry

## Roadmap

The current native executable is **one simple playable game**, not an
era-specific production game builder. Follow-on capabilities include
authorable game project files, asset pipelines with explicit source
rights, controller abstraction, game saves, sound and animation,
deterministic replay fixtures, platform-specific builds and emulation
harnesses. Proprietary console SDKs and copyrighted games should not
be bundled or scraped without appropriate permissions.

**Release status:** Changes are committed to PR #3593. The exact-head
P2 Local Inference, Windows Installer, App Assembly and Merge Readiness
gates must pass, and a real Windows user must verify the graphical
launcher before this feature can be signed as production-ready.
