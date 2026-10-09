# Executable CHIP-8 homebrew: first legal retro ROM completion lane

**2026-10-09 status:** Implemented as a genuine, self-contained, original
CHIP-8 bytecode compiler, interpreter and executable gameplay proof in
Skeleton PR #3593. Exact-head CI and real vintage hardware tests still
need separate validation. **CHIP-8 is a 1970s virtual machine, not a
Game Boy, NES, Xbox, PlayStation or contemporary Nintendo console.**

The design purpose is to close one platform's actual generation,
execution, gameplay and provenance loop before declaring the remaining
165 platform profiles finished. This implementation does not ship a
manufacturer's BIOS, console boot ROM, copyrighted Nintendo logo,
encryption keys, copied game images, proprietary SDK or licensed art.

## Original CHIP-8 game creation

From Skeleton's repository root:

\`\`\`sh
# Generates a real executable .ch8 file, tests the bytecode to victory
# on the in-repo VM, then writes a new output only after acceptance.
python scripts/game/export_chip8.py \
  --demo-rom --seed 42 --output my-original-game.ch8

# Or author an original RIGHTS-ATTESTED compact map capsule (5-8 tiles
# per side), then compile *that* project's original design:
python scripts/game/export_chip8.py \
  --capsule original-small-game.json --output my-game.ch8

# Installed Windows offline console:
SkeletonOffline.exe --chip8-demo-output my-original-game.ch8
SkeletonOffline.exe \
  --chip8-export-capsule original-small-game.json \
  --chip8-rom-output my-game.ch8

# Integrated application interface:
python -m skeleton app local-ai \
  --chip8-demo-output my-original-game.ch8
\`\`\`

The compiler emits actual classic CHIP-8 instructions (00E0, 1nnn,
3xkk, 6xkk, Annn, Dxyn, Fx0A), screen drawing, map collisions, keypad
movement, an input loop and a distinct winning screen. The original
map is compiled into a bounded jump-based cell state machine; there
is no embedded JavaScript, Python source, or proprietary engine.

**Controls:** keypad 4 = left, 6 = right, 8 = up, 2 = down.
CHIP-8 emulators usually map these hexadecimal keys onto computer
keyboard layouts. This exporter intentionally uses classic CHIP-8
keypad codes; gamepad remapping is emulator/device-specific.

### Actual executable acceptance

The independent \`Chip8Machine\` loads the emitted bytes at 0x200,
initializes a 4096-byte VM memory and 64x32 monochrome screen, executes
the ROM to its keypad wait, supplies a shortest source-map route, and
**requires the machine to reach the winning program address** within
finite instruction budgets. No platform firmware is loaded. It also
checks the ROM SHA-256 against its source receipt.

\`skeleton/testing/test_chip8_homebrew.py\` covers several seeds,
reproducibility, collision rejection at the spawn wall, VM opcode
admission, corrupt keyboard values, original asset restrictions,
source-provenance tampering and new-file-only output.

\`skeleton/testing/test_target_completion.py\` tests the release
completion gate and the ability to export from both the standard
offline console and the unified application CLI.

The Windows installer pipeline is required to:

1. Invoke the **installed \`SkeletonOffline.exe\`** to create an original
   CHIP-8 game ROM and verify the full VM execution receipt.
2. Verify the actual file's SHA-256 and enforce the 3584-byte maximum
   payload for a 4 KiB CHIP-8 machine starting at memory 0x200.
3. Regenerate the same original game in a different file using the
   **installed EXE again** and compare deterministic identity.
4. Reject overwriting an existing ROM and reject false claims of
   copyrighted firmware or SDK inclusion.

**The pipeline checks are commitments, not evidence of a passed
run until GitHub reports the successful exact PR head.** On an
emulator other than Skeleton's subset VM or vintage COSMAC VIP
hardware, compatibility and timing must be separately tested.

## Play the ROM in the native Skeleton desktop game

\`\`\`powershell
SkeletonGame.exe --chip8-demo
SkeletonOffline.exe --chip8-demo-check --json
\`\`\`

The first option opens a real native 64×32 CHIP-8 framebuffer with
keypad movement (arrow keys/WASD), **R** to restart and **Escape** to
quit. It executes the same generated original ROM as the standalone
compiler. It does not require an external emulator, HTML/web rendering,
protected firmware, downloaded art or a trained model.

The second command is an actual controller-to-win VM replay with no
display dependency, suitable for testing the installed executable.
The Windows installer workflow runs it and checks the ROM hash, win
state, rights limitations and zero training-data expansion.

The emulator also supports much more of the documented classic
instruction set: ALU, skips, subroutines, 16-depth stack, 60 Hz
explicit timer ticks, locally authored hexadecimal glyphs, keypad
held-key queries, BCD, store/load, deterministic RNG and configurable
shift/index-transfer/display-wrap quirks. Unsupported extensions
are refused instead of silently interpreted.

This is a **classic virtual-machine compatibility implementation**,
not a cycle-accurate original COSMAC VIP emulator. Original hardware
timing, external third-party ROM compatibility, 60 Hz wall-clock
scheduling, platform sound output and release compliance still need
separate proof.

## Readiness and genuinely remaining functionality

| Gate | Status |
| --- | --- |
| Original game tilemap and rights-attested provenance | Implemented |
| CHIP-8 bytecode compiler and executable ROM writer | Implemented |
| Memory-bounded interpreter for classic CHIP-8 instruction families | Implemented |
| Deterministic keypad movement, wall collision, win condition | Implemented |
| Offline replay of emitted ROM to victory | Implemented; CI verdict pending |
| Frozen Windows console export | Wired; installed CI verdict pending |
| Full external CHIP-8 emulator / hardware compatibility | Not verified |
| Timer/register/sprite/font/quirk instruction support | Implemented; regression CI pending |
| External 60 Hz scheduler, audible buzzer and cycle accuracy | Not yet validated |
| Super-CHIP/XO-CHIP extensions | Not implemented |
| Original device performance/timing/cycle accuracy | Not verified |
| Independently verified distribution license/asset ownership | Not verified |
| Human-approved publication and signed production release | Not completed |

The interpreter supports classic opcode families and all instructions
generated by the original homebrew compiler. It is intentionally not
advertised as cycle-accurate or fully compatible with all historical,
protected, Super-CHIP or XO-CHIP titles. Independent
legally obtained third-party games should **not** be imported into
this exporter under a guess of permission.

## Actual release completion ledger

\`\`\`sh
# All 166 named targets, with immutable machine-readable gate keys
# and honest completed/unfinished counts:
python scripts/game/verify_target_completion.py

# This actually generates and runs original CHIP-8 ROM bytes before
# reporting local executable proof.
python scripts/game/verify_target_completion.py \
  --target chip8-vip --prove-chip8

# Examine outstanding releases separately:
python scripts/game/verify_target_completion.py --target game-boy
python scripts/game/verify_target_completion.py --target playstation-5
\`\`\`

Eight gates are mandatory: real code emission, reproducible build,
executed acceptance, hardware or authorized emulator verification,
asset rights verification, toolchain license review, exact-head CI
success, and human release signoff. The release readiness gate stays
false until supported evidence exists; a digest or operator attestation
alone cannot mint permission to distribute.

Completion percentage here is **specific to fully signed platform
releases**, not a guess about code lines, broad AI competence or the
entire product. Adding profiles does not count as completing them.

## Model and training discipline

This is deterministic code, *not* an assertion that an untrained
consumer model now understands all games. It uses no network and adds
**zero** training records. The existing active sparse default remains
36 examples across 36 modes, with optional budget ceilings of 48/72.

For cross-era rights restrictions and official developer requirements,
see [Cross-Era Game Rights and Capabilities](
CROSS_ERA_GAME_RIGHTS_AND_CAPABILITIES.md).
