# Milestone: actually compiled lawful libretro ABI homebrew smoke fixture — October 15, 2026

**This milestone includes real local execution of a compiled native shared library.** It is **not** a commercial-console emulator, a downloaded ROM, a BIOS, or proof that the Linux Bubblewrap worker can run every core.

A small self-contained and legally original C source fixture, `tests/fixtures/homebrew_libretro_smoke.c`, exports the standard v1 libretro functions required by the Skeleton native worker. The binary is **never committed**, shipped in the installer, or installed as a console emulator. It is compiled under a temporary test directory with `cc -std=c11 -fPIC -shared -O2 -Wall -Wextra -Werror`, and discarded after the smoke test.

The test uses a 12-byte original marker (`SKL-HOMEBREW`) instead of a ROM. It checks:
- libretro API version and declared `.bin` content extension and system geometry/timing;
- core-provided `RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS` button labels;
- one actual native frame callback from the 32×24 RGB565 test output;
- 64 actual PCM stereo callback frames per `retro_run`, with no recorded licensed sound;
- a visual frame SHA change when simulated RetroPad A is pressed;
- a full savestate serialize / mutate / unserialize / replay round-trip, reproducing the same subsequent frame SHA;
- a readable bounded native memory region.

The parent `tests/test_game_emulator_homebrew_native_abi.py` compiles this C source and runs `tests/fixtures/verify_homebrew_libretro_smoke.py` in a separate, timeout-bound Python subprocess, so native assertion or segmentation failures do not kill the entire unit runner. Both source files are tracked; no executable artifact is stored in Git.

A local compile and direct ctypes-driven smoke run **did execute successfully** during this development pass: 21 standard exported functions, two core-reported button descriptions, four native frame/audio callbacks, input-dependent distinct frame hashes and exact deterministic savestate restore. The tracked subprocess test source was added to the manual-only focused qualification job; its exact CI execution is not yet confirmed.

**Unqualified remains:** actual Bubblewrap isolated host launch and IPC, integration with one of the approved source-pinned emulator cores, real legacy hardware fidelity, 169-platform completeness, real game copyright rights and measured model-weight improvement. This fixture proves an ABI foundation, not any commercial game playability.

## Linux-only full sandbox host qualification

A second test, `tests/test_game_emulator_homebrew_bwrap_host.py`, takes the exact same original C fixture through Skeleton's **real operator registry inspector and Bubblewrap worker transport**, not direct ctypes calls alone. It compiles a temporary native ELF, registers a test-only core identity via in-process-only metadata monkeypatch (never a production catalog entry), creates an exact SHA-pinned approved registry, and supplies only the 12-byte original homebrew marker as content.

If Linux, `cc`, and `bwrap` are installed, the test requests actual isolated worker reset, actual libretro metadata and controller descriptions, an input-induced RGB frame change, native PCM callback, and snapshot/restore frame reproducibility. Absence of these host prerequisites skips the test with an explicit reason; it does **not** silently report passed sandbox execution. The **manually triggered focused qualification workflow** installs Bubblewrap when needed before launching it. The exact Linux-host test result remains pending until that workflow runs and its native worker succeeds.

The fixture uses the NES inventory identity solely to satisfy the test-internal canonical-target schema; it is **not a NES core**, and its temporary test-only core ID is not included in source-pinned emulator recipes, normal registries or released hardware compatibility claims.
