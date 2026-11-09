# Native GameForge delivery recovery

**Date:** 2026-10-13
**Source:** PR #3593 at `7f9be557bac3a4108dfc683716b15437de30f547`
**Target:** current `main`, additive files only

The original homebrew editor and port renderer have a native Tk UI, independent
of LLM inference, browser services and third-party console SDKs. The dedicated
`packaging/windows/game_preview_entry.py` dispatches a seeded native preview,
original CHIP-8 game, a verified game project, or a rights-attested homebrew
editor/port from explicit command-line options. Contradictory CLI modes fail
before launching a GUI.

The `scripts/game/accept_game_builds.py` tool is an executable acceptance
driver. It requires a real compiler to claim ISO C89 success and actually
executes output code; it separately checks CHIP-8 executable behavior and
original deterministic preview. The original reproducible offline-game
fixture and a native-model smoke-fixture helper are restored, with the
source-pinned acceptance test plus new headless CLI routing regression tests.

## Maturity boundary

These Python modules are **not** proof a Windows `.exe` or installer has been
built or signed, and this tranche does not change the existing Windows
installer workflow or overwrite its current scripts. Real Windows runner
qualification, exact-head App Assembly, native GUI smoke, artifact provenance,
OS support and licensed release requirements still need separate evidence.
CHIP-8/C89 original-code paths do not imply compatibility with vendor ROMs,
consoles, or copyrighted art.

Use `python scripts/game/accept_game_builds.py` for supported on-host
executed acceptance; unavailable compilers must not be reported as success.
